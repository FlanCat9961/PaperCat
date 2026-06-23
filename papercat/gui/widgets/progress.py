from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from papercat.gui.i18n import t


class ProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("dialog.progress.title"))
        self.label = QLabel("")
        self.progress = QProgressBar()
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)

    def update_progress(self, message: str, value: int, maximum: int) -> None:
        self.label.setText(message)
        self.progress.setMaximum(maximum)
        self.progress.setValue(value)
