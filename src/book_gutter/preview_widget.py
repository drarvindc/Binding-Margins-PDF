from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from .content_bounds import ContentBoundsEstimate
from .pdf_transform import BindingSide, page_shift_sign, target_rect_for_page


@dataclass(frozen=True)
class PreviewState:
    page_index: int
    page_count: int
    scale: float
    shift_mm: float
    binding_side: BindingSide
    show_original: bool
    page_rect: fitz.Rect
    target_rect: fitz.Rect
    pixmap: fitz.Pixmap
    content_estimate: ContentBoundsEstimate


class PagePreviewWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 420)
        self._state: Optional[PreviewState] = None

    def set_state(self, state: Optional[PreviewState]) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # pragma: no cover - Qt paint
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#efefe9"))
        if not self._state:
            painter.setPen(QtGui.QColor("#666"))
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "Open a PDF to preview the page shift.")
            return

        state = self._state
        margin = 18
        available = self.rect().adjusted(margin, margin, -margin, -margin)
        page_width = state.page_rect.width
        page_height = state.page_rect.height
        scale = min(available.width() / page_width, available.height() / page_height)
        scale = max(scale, 0.01)
        draw_width = page_width * scale
        draw_height = page_height * scale
        origin_x = available.x() + (available.width() - draw_width) / 2.0
        origin_y = available.y() + (available.height() - draw_height) / 2.0
        page_rect = QtCore.QRectF(origin_x, origin_y, draw_width, draw_height)

        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        image = QtGui.QImage(state.pixmap.samples, state.pixmap.width, state.pixmap.height, state.pixmap.stride, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(image.copy())

        def map_rect(rect: fitz.Rect) -> QtCore.QRectF:
            left = origin_x + rect.x0 * scale
            top = origin_y + rect.y0 * scale
            return QtCore.QRectF(left, top, rect.width * scale, rect.height * scale)

        content_rect = map_rect(state.target_rect)
        painter.drawPixmap(content_rect, pixmap, QtCore.QRectF(0, 0, state.pixmap.width, state.pixmap.height))

        painter.setPen(QtGui.QPen(QtGui.QColor("#333"), 2))
        painter.drawRect(page_rect)

        strip_width = abs(state.shift_mm) * scale * 72.0 / 25.4
        if strip_width > 0:
            if page_shift_sign(state.page_index, state.binding_side) > 0:
                strip = QtCore.QRectF(page_rect.left(), page_rect.top(), strip_width, page_rect.height())
            else:
                strip = QtCore.QRectF(page_rect.right() - strip_width, page_rect.top(), strip_width, page_rect.height())
            painter.fillRect(strip, QtGui.QColor(70, 130, 180, 50))

        if state.show_original:
            painter.setPen(QtGui.QPen(QtGui.QColor("#c05621"), 2, QtCore.Qt.PenStyle.DashLine))
            original_rect = target_rect_for_page(state.page_rect, state.scale, 0.0, state.page_index, state.binding_side)
            painter.drawRect(map_rect(original_rect))
