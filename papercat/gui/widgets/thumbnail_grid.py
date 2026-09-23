from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

# Hover animation params (V0.2: slight lift + brightened border, 120ms easing).
HOVER_LIFT_PX = 4
HOVER_DURATION_MS = 120
ACCENT_COLOR = QColor("#cba6f7")
SELECT_COLOR = QColor("#cba6f7")

# Type alias matching Qt's delegate override signatures.
_Index = QModelIndex | QPersistentModelIndex


class ThumbnailDelegate(QStyledItemDelegate):
    """Per-item hover effect: lift the thumbnail and brighten its border over 120ms.

    progress 0..1 goes from rest to fully hovered; a single QVariantAnimation drives
    the current hover item, and paint() applies the lift offset and border alpha.
    """

    def __init__(self, view: QListView) -> None:
        super().__init__(view)
        self._view = view
        self._hover_index: _Index = QModelIndex()
        self._progress = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(HOVER_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_tick)

    def set_hover_index(self, index: _Index) -> None:
        if index == self._hover_index:
            return
        self._hover_index = QModelIndex(index)  # type: ignore[arg-type]
        # Restart from 0 toward 1; only the current hover item animates its lift.
        self._anim.stop()
        if index.isValid():
            self._anim.setDirection(QVariantAnimation.Direction.Forward)
            self._anim.start()
        else:
            self._progress = 0.0
            self._view.viewport().update()

    def _on_anim_tick(self, value: object) -> None:
        self._progress = float(value)  # type: ignore[arg-type]
        if self._hover_index.isValid():
            rect = self._view.visualRect(QModelIndex(self._hover_index))  # type: ignore[arg-type]
            self._view.viewport().update(rect.adjusted(-8, -HOVER_LIFT_PX - 4, 8, 8))
        else:
            self._view.viewport().update()

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: _Index
    ) -> None:
        is_hovered = index == self._hover_index
        progress = self._progress if is_hovered else 0.0
        lift = round(HOVER_LIFT_PX * progress)

        rect = QRect(option.rect)
        if lift:
            rect.translate(0, -lift)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Selection background.
        content_rect = rect.adjusted(6, 6, -6, -6)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(203, 166, 247, 40))
            painter.drawRoundedRect(content_rect.adjusted(-3, -3, 3, 3), 10, 10)

        # Draw the thumbnail centered in the content rect.
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon):
            size = icon.actualSize(content_rect.size())
            x = content_rect.x() + (content_rect.width() - size.width()) // 2
            y = content_rect.y() + (content_rect.height() - size.height()) // 2
            target = QRect(QPoint(x, y), size)
            icon.paint(painter, target, Qt.AlignmentFlag.AlignCenter)
            border_rect = target.adjusted(-2, -2, 2, 2)
        else:
            border_rect = content_rect

        # Brightened border: always on when selected, fades in with progress on hover.
        if selected:
            painter.setPen(QPen(SELECT_COLOR, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(border_rect, 8, 8)
        elif progress > 0.01:
            color = QColor(ACCENT_COLOR)
            color.setAlphaF(min(1.0, progress))
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(border_rect, 8, 8)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return QSize(280, 300)


class ThumbnailGrid(QListView):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ThumbnailGrid")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(256, 256))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)

        self._delegate = ThumbnailDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setMovement(QListView.Movement.Static)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        self._delegate.set_hover_index(index)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._delegate.set_hover_index(QModelIndex())
        super().leaveEvent(event)
