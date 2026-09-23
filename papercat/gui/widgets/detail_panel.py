from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from papercat.gui.i18n import t


class DetailPanel(QFrame):
    """Detail drawer: real image preview, metadata, keep/delete.

    Used as an overlay drawer positioned and animated by MainWindow.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailDrawer")

        # Top row: title + close
        header = QHBoxLayout()
        title = QLabel(t("detail.title"))
        title.setObjectName("DrawerTitle")
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("DrawerClose")
        self.close_button.setFixedSize(28, 28)
        header.addWidget(title, 1)
        header.addWidget(self.close_button)

        # Image preview
        self.preview = QLabel(t("detail.empty"))
        self.preview.setObjectName("PreviewImage")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(280)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setWordWrap(True)

        # Metadata
        self.metadata = QLabel("")
        self.metadata.setObjectName("Metadata")
        self.metadata.setWordWrap(True)
        self.metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Action buttons
        self.keep_button = QPushButton(t("action.keep"))
        self.delete_button = QPushButton(t("action.delete"))
        buttons = QHBoxLayout()
        buttons.addWidget(self.keep_button)
        buttons.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.metadata)
        layout.addLayout(buttons)

        self._pixmap: QPixmap | None = None

    def set_image(self, path: Path | None) -> None:
        """Load the real image and scale it to fit the preview area."""
        if path is None or not Path(path).exists():
            self._pixmap = None
            self.preview.setText(t("detail.empty"))
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._pixmap = None
            self.preview.setText(t("detail.load_failed"))
            return
        self._pixmap = pixmap
        self._rescale_preview()

    def clear_image(self) -> None:
        self._pixmap = None
        self.preview.setText(t("detail.empty"))

    def _rescale_preview(self) -> None:
        if self._pixmap is None:
            return
        target = self.preview.size()
        scaled = self._pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rescale_preview()
