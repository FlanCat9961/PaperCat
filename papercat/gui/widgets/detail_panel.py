from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from papercat.gui.i18n import t


class DetailPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DetailPanel")
        self.preview = QLabel(t("detail.empty"))
        self.metadata = QLabel("")
        self.keep_button = QPushButton(t("action.keep"))
        self.delete_button = QPushButton(t("action.delete"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.metadata)
        layout.addWidget(self.keep_button)
        layout.addWidget(self.delete_button)
