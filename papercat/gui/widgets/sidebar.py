from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from papercat.gui.i18n import t

SOURCE_FILTER_ALL = "__all__"


class Sidebar(QFrame):
    """Sidebar: subscription list + filter area (kept-only / NSFW / by-source / by-subscription).

    Emits filters_changed when any filter toggles; crawl_subscription_requested on
    right-click "crawl this subscription".
    """

    filters_changed = Signal()
    crawl_subscription_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")

        # Subscription list
        self.subscriptions = QListWidget()
        self.subscriptions.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.subscriptions.customContextMenuRequested.connect(self._on_context_menu)

        self.add_button = QPushButton(t("sidebar.add_sub"))
        self.edit_button = QPushButton(t("sidebar.edit_sub"))
        self.delete_button = QPushButton(t("sidebar.delete_sub"))

        # Filters
        self.kept_only = QCheckBox(t("filter.kept_only"))
        self.nsfw_toggle = QCheckBox(t("settings.nsfw"))
        self.sub_filter = QCheckBox(t("filter.by_subscription"))
        self.source_filter = QComboBox()
        self.source_filter.addItem(t("filter.source_all"), SOURCE_FILTER_ALL)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        layout.addWidget(_section_label(t("sidebar.subscriptions")))
        layout.addWidget(self.subscriptions, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

        layout.addSpacing(8)
        layout.addWidget(_section_label(t("sidebar.filters")))
        layout.addWidget(self.kept_only)
        layout.addWidget(self.nsfw_toggle)
        layout.addWidget(self.sub_filter)
        layout.addWidget(QLabel(t("filter.source")))
        layout.addWidget(self.source_filter)

        # Filter changes trigger refresh.
        self.kept_only.toggled.connect(self.filters_changed)
        self.nsfw_toggle.toggled.connect(self.filters_changed)
        self.sub_filter.toggled.connect(self.filters_changed)
        self.source_filter.currentIndexChanged.connect(self.filters_changed)
        self.subscriptions.currentItemChanged.connect(self._on_sub_selection_changed)

    def _on_sub_selection_changed(self) -> None:
        # Only refresh when "filter by subscription" is active.
        if self.sub_filter.isChecked():
            self.filters_changed.emit()

    def _on_context_menu(self, pos: QPoint) -> None:
        from PySide6.QtWidgets import QMenu

        item = self.subscriptions.itemAt(pos)
        if item is None:
            return
        sub_id = item.data(Qt.ItemDataRole.UserRole)
        if sub_id is None:
            return
        menu = QMenu(self)
        crawl_action = menu.addAction(t("sidebar.crawl_this"))
        chosen = menu.exec(self.subscriptions.mapToGlobal(pos))
        if chosen == crawl_action:
            self.crawl_subscription_requested.emit(int(sub_id))

    def set_sources(self, sources: list[str]) -> None:
        """Populate the source combobox from current library records.

        Preserves the current selection if it still exists.
        """
        current = self.source_filter.currentData()
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem(t("filter.source_all"), SOURCE_FILTER_ALL)
        for src in sources:
            self.source_filter.addItem(src, src)
        idx = self.source_filter.findData(current)
        self.source_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.source_filter.blockSignals(False)

    def selected_source(self) -> str | None:
        data = self.source_filter.currentData()
        return None if data == SOURCE_FILTER_ALL else data


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    return label
