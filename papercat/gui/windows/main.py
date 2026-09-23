from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve,
    QModelIndex,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from papercat.core.cleaner import CleanupReport
from papercat.core.crawler import CrawlReport, ProgressEvent
from papercat.core.library import WallpaperRecord
from papercat.core.types import NsfwLevel
from papercat.gui.i18n import t
from papercat.gui.widgets.detail_panel import DetailPanel
from papercat.gui.widgets.progress import ProgressDialog
from papercat.gui.widgets.sidebar import Sidebar
from papercat.gui.widgets.thumbnail_grid import ThumbnailGrid
from papercat.gui.windows.settings import SettingsDialog
from papercat.gui.windows.subscription_editor import SubscriptionEditorDialog

if TYPE_CHECKING:
    from papercat.gui.app import AppControllers


ROLE_WALLPAPER_ID = Qt.ItemDataRole.UserRole + 1
LOGGER = logging.getLogger(__name__)

DRAWER_WIDTH = 380
DRAWER_ANIM_MS = 200

# Compact top offset to avoid calculating HeaderBar runtime height.
HEADER_TOP = 84


class BackgroundWidget(QWidget):
    """Fixed dark gradient-blur background (simulates glassmorphism inside the window).

    Wayland does not support real backdrop blur; we use a dark gradient with soft
    accent-colour glows, cached as a pixmap.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RootSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._cache: QPixmap | None = None
        self._cache_size = QSize()

    def _build(self, size: QSize) -> QPixmap:
        pixmap = QPixmap(size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = size.width(), size.height()

        # Vertical dark gradient.
        grad = QLinearGradient(0, 0, w * 0.4, h)
        grad.setColorAt(0.0, QColor("#181825"))
        grad.setColorAt(0.5, QColor("#1e1e2e"))
        grad.setColorAt(1.0, QColor("#11111b"))
        painter.fillRect(0, 0, w, h, grad)

        # Two soft accent-colour glows for depth.
        for cx, cy, radius, color in (
            (w * 0.18, h * 0.12, max(w, h) * 0.45, QColor(203, 166, 247, 46)),
            (w * 0.88, h * 0.85, max(w, h) * 0.5, QColor(137, 180, 250, 38)),
        ):
            radial = QRadialGradient(cx, cy, radius)
            radial.setColorAt(0.0, color)
            transparent = QColor(color)
            transparent.setAlpha(0)
            radial.setColorAt(1.0, transparent)
            painter.fillRect(0, 0, w, h, radial)

        painter.end()
        return pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._cache is None or self._cache_size != self.size():
            self._cache = self._build(self.size())
            self._cache_size = self.size()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)


class MainWindow(QMainWindow):
    def __init__(self, controllers: AppControllers | None = None) -> None:
        super().__init__()
        self.controllers = controllers
        self.setWindowTitle(t("app.title"))
        self.resize(1280, 820)

        # Background layer.
        self.background = BackgroundWidget()
        root = self.background
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # Header.
        header = QFrame()
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        title = QLabel(t("app.title"))
        title.setObjectName("Title")
        self.crawl_all_button = QPushButton(t("action.crawl_all"))
        self.crawl_all_button.setObjectName("Accent")
        self.crawl_selected_button = QPushButton(t("action.crawl_selected"))
        self.refresh_button = QPushButton(t("action.refresh"))
        self.cleanup_button = QPushButton(t("action.cleanup"))
        self.settings_button = QPushButton(t("action.settings"))
        header_layout.addWidget(title, 1)
        header_layout.addWidget(self.crawl_all_button)
        header_layout.addWidget(self.crawl_selected_button)
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.cleanup_button)
        header_layout.addWidget(self.settings_button)

        # Content: sidebar + grid (drawer is an overlay outside the layout).
        content = QHBoxLayout()
        content.setSpacing(12)
        self.sidebar = Sidebar()
        self.grid = ThumbnailGrid()
        self.sidebar.setFixedWidth(280)
        content.addWidget(self.sidebar)
        content.addWidget(self.grid, 1)

        outer.addWidget(header)
        outer.addLayout(content, 1)
        self.setCentralWidget(root)

        # Detail drawer: overlay positioned manually, slides in/out.
        self.detail = DetailPanel(self.background)
        shadow = QGraphicsDropShadowEffect(self.detail)
        shadow.setBlurRadius(36)
        shadow.setOffset(-6, 0)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.detail.setGraphicsEffect(shadow)
        self.detail.hide()
        self._drawer_anim = QPropertyAnimation(self.detail, b"geometry", self)
        self._drawer_anim.setDuration(DRAWER_ANIM_MS)
        self._drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drawer_open = False

        self.model = QStandardItemModel(self)
        self.grid.setModel(self.model)
        self._records: dict[int, WallpaperRecord] = {}
        self._current_id: int | None = None
        self._progress_dialog: ProgressDialog | None = None

        # Signal connections.
        self.refresh_button.clicked.connect(self.refresh)
        self.crawl_all_button.clicked.connect(self._on_crawl_all)
        self.crawl_selected_button.clicked.connect(self._on_crawl_selected)
        self.cleanup_button.clicked.connect(self._on_cleanup_clicked)
        self.settings_button.clicked.connect(self._on_settings_clicked)
        self.detail.keep_button.clicked.connect(self._on_toggle_kept)
        self.detail.delete_button.clicked.connect(self._on_delete_clicked)
        self.detail.close_button.clicked.connect(self._close_drawer)
        selection = self.grid.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._on_selection_changed)
        self.sidebar.add_button.clicked.connect(self._on_sub_add)
        self.sidebar.edit_button.clicked.connect(self._on_sub_edit)
        self.sidebar.delete_button.clicked.connect(self._on_sub_delete)
        self.sidebar.filters_changed.connect(self.refresh)
        self.sidebar.crawl_subscription_requested.connect(self._on_crawl_subscription)

        if self.controllers is not None:
            self.refresh()

    # ---- Data refresh ----

    def _active_nsfw_levels(self) -> set[NsfwLevel] | None:
        if self.sidebar.nsfw_toggle.isChecked():
            return None  # All levels.
        return {NsfwLevel.SFW}

    def refresh(self) -> None:
        if self.controllers is None:
            return
        kept_only = self.sidebar.kept_only.isChecked()
        records = self.controllers.library.list_wallpapers(
            nsfw_levels=self._active_nsfw_levels(),
            is_kept=True if kept_only else None,
        )

        # Client-side filtering: by source / by subscription.
        source = self.sidebar.selected_source()
        if source is not None:
            records = [r for r in records if r.source == source]
        if self.sidebar.sub_filter.isChecked():
            sub_id = self._selected_sub_id()
            if sub_id is not None:
                records = [r for r in records if r.subscription_id == sub_id]

        self.model.clear()
        self._records.clear()
        for record in records:
            item = QStandardItem(record.filename)
            item.setEditable(False)
            item.setData(record.id, ROLE_WALLPAPER_ID)
            try:
                thumb = self.controllers.library.thumbnail_path(record.id)
                item.setIcon(QIcon(str(thumb)))
            except Exception as exc:
                LOGGER.warning("thumbnail generation failed for %s: %s", record.id, exc)
            item.setSizeHint(QSize(280, 300))
            self.model.appendRow(item)
            self._records[record.id] = record

        self._refresh_sidebar()
        if self._current_id not in self._records:
            self._close_drawer()

    def _refresh_sidebar(self) -> None:
        if self.controllers is None:
            return
        from PySide6.QtWidgets import QListWidgetItem

        previous = self._selected_sub_id()
        self.sidebar.subscriptions.blockSignals(True)
        self.sidebar.subscriptions.clear()
        for sub in self.controllers.subscription.list():
            item = QListWidgetItem(sub.name)
            item.setData(Qt.ItemDataRole.UserRole, sub.id)
            self.sidebar.subscriptions.addItem(item)
            if sub.id == previous:
                self.sidebar.subscriptions.setCurrentItem(item)
        self.sidebar.subscriptions.blockSignals(False)

        # Source dropdown populated from current library records.
        sources = sorted({r.source for r in self._records.values()})
        self.sidebar.set_sources(sources)

    # ---- Detail drawer ----

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        wallpaper_id = current.data(ROLE_WALLPAPER_ID)
        record = self._records.get(int(wallpaper_id)) if wallpaper_id is not None else None
        if record is None:
            return
        self._render_detail(record)
        self._open_drawer()

    def _render_detail(self, record: WallpaperRecord) -> None:
        self._current_id = record.id
        meta_lines = [
            f"{t('detail.resolution')}: {record.width}x{record.height}",
            f"{t('detail.source')}: {record.source}",
            f"{t('detail.subscription')}: {record.subscription_name or '-'}",
            f"{t('detail.tags')}: {', '.join(record.tags) if record.tags else '-'}",
        ]
        self.detail.metadata.setText("\n".join(meta_lines))
        self.detail.set_image(record.path)
        self.detail.keep_button.setText(
            t("action.unkeep") if record.is_kept else t("action.keep")
        )
        self.detail.keep_button.setEnabled(True)
        self.detail.delete_button.setEnabled(True)

    def _drawer_rect(self, visible: bool) -> QRect:
        area = self.background.rect()
        height = area.height() - HEADER_TOP - 12
        x = area.width() - DRAWER_WIDTH - 12 if visible else area.width()
        return QRect(x, HEADER_TOP, DRAWER_WIDTH, height)

    def _open_drawer(self) -> None:
        self.detail.show()
        self.detail.raise_()
        start = self.detail.geometry() if self._drawer_open else self._drawer_rect(False)
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(start)
        self._drawer_anim.setEndValue(self._drawer_rect(True))
        self._drawer_anim.start()
        self._drawer_open = True

    def _close_drawer(self) -> None:
        self._current_id = None
        if not self._drawer_open:
            self.detail.hide()
            return
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(self.detail.geometry())
        self._drawer_anim.setEndValue(self._drawer_rect(False))
        with contextlib.suppress(RuntimeError, TypeError):
            self._drawer_anim.finished.disconnect()
        self._drawer_anim.finished.connect(self._on_drawer_closed)
        self._drawer_anim.start()
        self._drawer_open = False
        self.grid.clearSelection()

    def _on_drawer_closed(self) -> None:
        if not self._drawer_open:
            self.detail.hide()
        with contextlib.suppress(RuntimeError, TypeError):
            self._drawer_anim.finished.disconnect(self._on_drawer_closed)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.detail.isVisible():
            self.detail.setGeometry(self._drawer_rect(self._drawer_open))

    # ---- Keep / delete ----

    def _on_toggle_kept(self) -> None:
        if self.controllers is None or self._current_id is None:
            return
        self.controllers.library.toggle_kept(self._current_id)
        self.refresh()

    def _on_delete_clicked(self) -> None:
        if self.controllers is None or self._current_id is None:
            return
        confirm = QMessageBox.question(
            self,
            t("dialog.confirm.title"),
            t("dialog.confirm.delete").format(n=1),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.controllers.library.delete([self._current_id])
        self._close_drawer()
        self.refresh()

    # ---- Crawl ----

    def _start_crawl(self, sub_ids: list[int]) -> None:
        if self.controllers is None:
            return
        if self.controllers.crawl.is_busy():
            return
        if not sub_ids:
            QMessageBox.information(self, t("app.title"), t("status.no_subs"))
            return

        dialog = ProgressDialog(self)
        dialog.label.setText(t("status.crawling"))
        dialog.progress.setRange(0, 0)
        dialog.show()
        self._progress_dialog = dialog

        def on_progress(event: ProgressEvent) -> None:
            if self._progress_dialog is None:
                return
            if event.type == "sub_progress" and event.target:
                self._progress_dialog.update_progress(
                    f"{event.subscription_name}: {event.downloaded}/{event.target}",
                    event.downloaded,
                    event.target,
                )
            elif event.subscription_name:
                self._progress_dialog.label.setText(event.subscription_name)

        def on_done(report: CrawlReport) -> None:
            if self._progress_dialog is not None:
                self._progress_dialog.close()
                self._progress_dialog = None
            QMessageBox.information(
                self,
                t("status.done"),
                t("status.crawl_result").format(
                    downloaded=report.total_downloaded,
                    failures=report.total_failures,
                ),
            )
            self.refresh()

        self.controllers.crawl.start(sub_ids, on_progress=on_progress, on_done=on_done)

    def _on_crawl_all(self) -> None:
        if self.controllers is None:
            return
        subs = self.controllers.subscription.list(enabled_only=True)
        self._start_crawl([sub.id for sub in subs])

    def _on_crawl_selected(self) -> None:
        sub_id = self._selected_sub_id()
        if sub_id is None:
            QMessageBox.information(self, t("app.title"), t("status.no_sub_selected"))
            return
        self._start_crawl([sub_id])

    def _on_crawl_subscription(self, sub_id: int) -> None:
        self._start_crawl([sub_id])

    # ---- Cleanup ----

    def _on_cleanup_clicked(self) -> None:
        if self.controllers is None:
            return
        victims = self.controllers.library.list_wallpapers(is_kept=False)
        if not victims:
            QMessageBox.information(self, t("app.title"), t("status.nothing_to_clean"))
            return
        confirm = QMessageBox.question(
            self,
            t("dialog.confirm.title"),
            t("dialog.confirm.cleanup").format(n=len(victims)),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        dialog = ProgressDialog(self)
        dialog.label.setText(t("status.cleaning"))
        dialog.progress.setRange(0, 0)
        dialog.show()
        self._progress_dialog = dialog

        def on_done(report: CleanupReport) -> None:
            if self._progress_dialog is not None:
                self._progress_dialog.close()
                self._progress_dialog = None
            QMessageBox.information(
                self,
                t("status.done"),
                t("status.cleanup_result").format(n=report.result.deleted_count),
            )
            self.refresh()

        self.controllers.cleanup.start_manual(
            [v.id for v in victims], on_done=on_done
        )

    # ---- Settings ----

    def _on_settings_clicked(self) -> None:
        if self.controllers is None:
            return
        dialog = SettingsDialog(self)
        dialog.bind(self.controllers.settings)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.refresh()

    # ---- Subscription management ----

    def _selected_sub_id(self) -> int | None:
        item = self.sidebar.subscriptions.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _on_sub_add(self) -> None:
        if self.controllers is None:
            return
        dialog = SubscriptionEditorDialog(self)
        dialog.bind(self.controllers)
        if dialog.exec() == SubscriptionEditorDialog.DialogCode.Accepted:
            sub = dialog.build_subscription()
            if sub is not None:
                try:
                    self.controllers.subscription.create(sub)
                except Exception as exc:
                    QMessageBox.warning(self, t("dialog.error.title"), str(exc))
                self._refresh_sidebar()

    def _on_sub_edit(self) -> None:
        if self.controllers is None:
            return
        sub_id = self._selected_sub_id()
        if sub_id is None:
            return
        current = next((s for s in self.controllers.subscription.list() if s.id == sub_id), None)
        if current is None:
            return
        dialog = SubscriptionEditorDialog(self)
        dialog.bind(self.controllers, current)
        if dialog.exec() == SubscriptionEditorDialog.DialogCode.Accepted:
            updated = dialog.build_subscription()
            if updated is not None:
                try:
                    self.controllers.subscription.update(updated)
                except Exception as exc:
                    QMessageBox.warning(self, t("dialog.error.title"), str(exc))
                self._refresh_sidebar()

    def _on_sub_delete(self) -> None:
        if self.controllers is None:
            return
        sub_id = self._selected_sub_id()
        if sub_id is None:
            return
        self.controllers.subscription.delete(sub_id)
        self._refresh_sidebar()
