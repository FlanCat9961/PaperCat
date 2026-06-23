from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QListView


class ThumbnailGrid(QListView):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ThumbnailGrid")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(256, 256))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
