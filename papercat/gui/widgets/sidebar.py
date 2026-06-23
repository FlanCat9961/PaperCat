from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from papercat.gui.i18n import t


class Sidebar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.subscriptions = QListWidget()
        self.nsfw_toggle = QCheckBox(t("settings.nsfw"))
        self.add_button = QPushButton(t("sidebar.add_sub"))
        self.edit_button = QPushButton(t("sidebar.edit_sub"))
        self.delete_button = QPushButton(t("sidebar.delete_sub"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("sidebar.subscriptions")))
        layout.addWidget(self.subscriptions, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)
        layout.addWidget(QLabel(t("sidebar.filters")))
        layout.addWidget(self.nsfw_toggle)
