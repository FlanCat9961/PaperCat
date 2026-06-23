from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from papercat.core.crawler import CrawlReport, ProgressEvent
from papercat.core.library import WallpaperRecord
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


class MainWindow(QMainWindow):
    def __init__(self, controllers: AppControllers | None = None) -> None:
        super().__init__()
        self.controllers = controllers
        self.setWindowTitle(t("app.title"))
        self.resize(1280, 820)

        root = QWidget()
        outer = QVBoxLayout(root)
        header = QFrame()
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        title = QLabel(t("app.title"))
        title.setObjectName("Title")
        self.crawl_button = QPushButton(t("action.crawl_all"))
        self.refresh_button = QPushButton(t("action.refresh"))
        self.settings_button = QPushButton(t("action.settings"))
        header_layout.addWidget(title, 1)
        header_layout.addWidget(self.crawl_button)
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.settings_button)

        content = QHBoxLayout()
        self.sidebar = Sidebar()
        self.grid = ThumbnailGrid()
        self.detail = DetailPanel()
        self.sidebar.setFixedWidth(280)
        self.detail.setFixedWidth(360)
        content.addWidget(self.sidebar)
        content.addWidget(self.grid, 1)
        content.addWidget(self.detail)

        outer.addWidget(header)
        outer.addLayout(content, 1)
        self.setCentralWidget(root)

        self.model = QStandardItemModel(self)
        self.grid.setModel(self.model)
        self._records: dict[int, WallpaperRecord] = {}
        self._current_id: int | None = None
        self._progress_dialog: ProgressDialog | None = None

        self.refresh_button.clicked.connect(self.refresh)
        self.crawl_button.clicked.connect(self._on_crawl_clicked)
        self.settings_button.clicked.connect(self._on_settings_clicked)
        self.detail.keep_button.clicked.connect(self._on_toggle_kept)
        self.detail.delete_button.clicked.connect(self._on_delete_clicked)
        selection = self.grid.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._on_selection_changed)
        self.sidebar.add_button.clicked.connect(self._on_sub_add)
        self.sidebar.edit_button.clicked.connect(self._on_sub_edit)
        self.sidebar.delete_button.clicked.connect(self._on_sub_delete)

        if self.controllers is not None:
            self.refresh()

    def refresh(self) -> None:
        if self.controllers is None:
            return
        self.model.clear()
        self._records.clear()
        records = self.controllers.library.list_wallpapers()
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
        self._render_detail(None)

    def _refresh_sidebar(self) -> None:
        if self.controllers is None:
            return
        self.sidebar.subscriptions.clear()
        for sub in self.controllers.subscription.list():
            from PySide6.QtWidgets import QListWidgetItem

            item = QListWidgetItem(sub.name)
            item.setData(Qt.ItemDataRole.UserRole, sub.id)
            self.sidebar.subscriptions.addItem(item)

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self._render_detail(None)
            return
        wallpaper_id = current.data(ROLE_WALLPAPER_ID)
        record = self._records.get(int(wallpaper_id)) if wallpaper_id is not None else None
        self._render_detail(record)

    def _render_detail(self, record: WallpaperRecord | None) -> None:
        self._current_id = record.id if record else None
        if record is None:
            self.detail.preview.setText(t("detail.empty"))
            self.detail.metadata.setText("")
            self.detail.keep_button.setEnabled(False)
            self.detail.delete_button.setEnabled(False)
            return
        meta_lines = [
            f"{t('detail.resolution')}: {record.width}x{record.height}",
            f"{t('detail.source')}: {record.source}",
            f"{t('detail.subscription')}: {record.subscription_name or '-'}",
            f"{t('detail.tags')}: {', '.join(record.tags) if record.tags else '-'}",
        ]
        self.detail.metadata.setText("\n".join(meta_lines))
        self.detail.preview.setText(record.filename)
        self.detail.keep_button.setText(t("action.unkeep") if record.is_kept else t("action.keep"))
        self.detail.keep_button.setEnabled(True)
        self.detail.delete_button.setEnabled(True)

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
        self.refresh()

    def _on_crawl_clicked(self) -> None:
        if self.controllers is None:
            return
        if self.controllers.crawl.is_busy():
            return
        subs = self.controllers.subscription.list(enabled_only=True)
        if not subs:
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

        self.controllers.crawl.start(
            [sub.id for sub in subs], on_progress=on_progress, on_done=on_done
        )

    def _on_settings_clicked(self) -> None:
        if self.controllers is None:
            return
        dialog = SettingsDialog(self)
        dialog.bind(self.controllers.settings)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.refresh()

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
