from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from .page_side import PageSide
from .pdf_transform import BindingSide, target_rect_for_page


class PreviewMode(str, Enum):
    SINGLE_PAGE = "single_page"
    FACING_PAGES = "facing_pages"


@dataclass(frozen=True)
class PreviewPage:
    page_number: int | None
    page_index: int | None
    page_rect: fitz.Rect
    target_rect: fitz.Rect | None
    pixmap: fitz.Pixmap | None
    title_text: str
    summary_text: str
    is_placeholder: bool = False
    page_side: PageSide | None = None


@dataclass(frozen=True)
class PreviewState:
    mode: PreviewMode
    page_count: int
    active_page_number: int
    indicator_text: str
    note_text: str
    scale: float
    binding_side: BindingSide
    show_original_position: bool
    show_binding_space: bool
    pages: tuple[PreviewPage, ...]


@dataclass(frozen=True)
class PreviewHitRegion:
    page_number: int | None
    rect: QtCore.QRectF
    is_placeholder: bool


@dataclass(frozen=True)
class _LayoutEntry:
    page: PreviewPage
    page_rect: QtCore.QRectF
    caption_rect: QtCore.QRectF
    title_rect: QtCore.QRectF
    summary_rect: QtCore.QRectF


class PagePreviewWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 480)
        self._state: Optional[PreviewState] = None
        self._layout: list[_LayoutEntry] = []
        self._hit_regions: list[PreviewHitRegion] = []

    page_clicked = QtCore.Signal(int)

    def set_state(self, state: Optional[PreviewState]) -> None:
        self._state = state
        self._rebuild_layout()
        self.update()

    def hit_regions(self) -> tuple[PreviewHitRegion, ...]:
        if self._state is not None and not self._layout:
            self._rebuild_layout()
        return tuple(self._hit_regions)

    def page_hit_regions(self) -> dict[int, QtCore.QRectF]:
        return {
            region.page_number: region.rect
            for region in self.hit_regions()
            if region.page_number is not None and not region.is_placeholder
        }

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # pragma: no cover - Qt event
        super().resizeEvent(event)
        self._rebuild_layout()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # pragma: no cover - Qt event
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        position = event.position()
        for region in self._hit_regions:
            if region.page_number is not None and not region.is_placeholder and region.rect.contains(position):
                self.page_clicked.emit(region.page_number)
                return
        super().mousePressEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # pragma: no cover - Qt paint
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QtGui.QColor("#f1efe9"))

        if not self._state:
            painter.setPen(QtGui.QColor("#666"))
            painter.drawText(
                self.rect(),
                QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
                "Open a PDF to preview the page shift.",
            )
            return

        if not self._layout:
            self._rebuild_layout()

        state = self._state
        self._draw_binding_space(painter, state)

        for entry in self._layout:
            self._draw_page(painter, state, entry)

    def _draw_binding_space(self, painter: QtGui.QPainter, state: PreviewState) -> None:
        if state.mode != PreviewMode.FACING_PAGES or not state.show_binding_space or len(self._layout) < 2:
            return
        left = self._layout[0].page_rect
        right = self._layout[1].page_rect
        gap_left = min(left.right(), right.left())
        gap_right = max(left.right(), right.left())
        if gap_right <= gap_left:
            return
        top = min(left.top(), right.top())
        bottom = max(left.bottom(), right.bottom())
        gap_rect = QtCore.QRectF(gap_left, top, gap_right - gap_left, bottom - top)

        gradient = QtGui.QLinearGradient(gap_rect.left(), 0.0, gap_rect.right(), 0.0)
        gradient.setColorAt(0.0, QtGui.QColor(0, 0, 0, 18))
        gradient.setColorAt(0.5, QtGui.QColor(255, 255, 255, 70))
        gradient.setColorAt(1.0, QtGui.QColor(0, 0, 0, 18))
        painter.fillRect(gap_rect, gradient)

    def _draw_page(self, painter: QtGui.QPainter, state: PreviewState, entry: _LayoutEntry) -> None:
        page = entry.page
        rect = entry.page_rect
        shadow_rect = rect.translated(5.0, 5.0)
        painter.fillRect(shadow_rect, QtGui.QColor(0, 0, 0, 28))

        if page.is_placeholder:
            painter.fillRect(rect, QtGui.QColor("#f8f6f1"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#b7aea1"), 2, QtCore.Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect, 6.0, 6.0)
        else:
            painter.fillRect(rect, QtGui.QColor("#ffffff"))
            if page.pixmap is not None and page.target_rect is not None:
                widget_target = self._map_source_rect(page.page_rect, rect, page.target_rect)
                painter.drawPixmap(widget_target, self._pixmap_to_qpixmap(page.pixmap), QtCore.QRectF(0, 0, page.pixmap.width, page.pixmap.height))
            painter.setPen(QtGui.QPen(QtGui.QColor("#d2ccc1"), 1))
            painter.drawRoundedRect(rect, 6.0, 6.0)

        if page.page_number == state.active_page_number:
            painter.setPen(QtGui.QPen(QtGui.QColor("#2f6df6"), 3))
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor("#4f4f4f" if page.is_placeholder else "#3c3c3c"), 1.5))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        if not page.is_placeholder and state.show_original_position and page.page_index is not None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#d13b3b"), 2, QtCore.Qt.PenStyle.DashLine))
            if page.page_side is not None:
                original_rect = target_rect_for_page(page.page_rect, state.scale, 0.0, page.page_side, state.binding_side)
                painter.drawRoundedRect(self._map_source_rect(page.page_rect, rect, original_rect).adjusted(-1.0, -1.0, 1.0, 1.0), 4.0, 4.0)

        self._draw_caption(painter, entry, page, page.page_number == state.active_page_number)

    def _draw_caption(self, painter: QtGui.QPainter, entry: _LayoutEntry, page: PreviewPage, is_active: bool) -> None:
        bg = QtGui.QColor("#ffffff")
        bg.setAlpha(215)
        painter.fillRect(entry.caption_rect, bg)
        border_color = QtGui.QColor("#d8d2c5")
        if is_active:
            border_color = QtGui.QColor("#2f6df6")
        painter.setPen(QtGui.QPen(border_color, 1))
        painter.drawRoundedRect(entry.caption_rect, 6.0, 6.0)

        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(max(8, title_font.pointSize()))
        painter.setFont(title_font)
        painter.setPen(QtGui.QColor("#1f2933"))
        if page.summary_text:
            painter.drawText(
                entry.title_rect,
                QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.TextFlag.TextWordWrap,
                page.title_text,
            )

            summary_font = painter.font()
            summary_font.setBold(False)
            summary_font.setPointSize(max(8, summary_font.pointSize() - 1))
            painter.setFont(summary_font)
            painter.setPen(QtGui.QColor("#45515f"))
            painter.drawText(
                entry.summary_rect,
                QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.TextFlag.TextWordWrap,
                page.summary_text,
            )
        else:
            painter.drawText(
                entry.caption_rect.adjusted(8.0, 4.0, -8.0, -4.0),
                QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.TextFlag.TextWordWrap,
                page.title_text,
            )

    def _rebuild_layout(self) -> None:
        self._layout = []
        self._hit_regions = []
        state = self._state
        if state is None:
            return

        margin = 18.0
        available = self.rect().adjusted(margin, margin, -margin, -margin)
        if available.width() <= 0 or available.height() <= 0:
            return

        if state.mode == PreviewMode.SINGLE_PAGE:
            self._layout = self._single_layout(state, available)
        else:
            self._layout = self._facing_layout(state, available)

        for entry in self._layout:
            self._hit_regions.append(PreviewHitRegion(entry.page.page_number, entry.page_rect, entry.page.is_placeholder))

    def _single_layout(self, state: PreviewState, available: QtCore.QRectF) -> list[_LayoutEntry]:
        page = state.pages[0]
        caption_height = 50.0
        page_area = QtCore.QRectF(available.left(), available.top(), available.width(), max(1.0, available.height() - caption_height))
        scale = min(page_area.width() / page.page_rect.width, page_area.height() / page.page_rect.height)
        scale = max(scale, 0.01)

        page_width = page.page_rect.width * scale
        page_height = page.page_rect.height * scale
        page_left = page_area.left() + (page_area.width() - page_width) / 2.0
        page_top = page_area.top() + (page_area.height() - page_height) / 2.0
        page_rect = QtCore.QRectF(page_left, page_top, page_width, page_height)
        caption_rect = QtCore.QRectF(page_rect.left(), page_rect.bottom() + 6.0, page_rect.width(), caption_height - 6.0)
        return [
            _LayoutEntry(
                page=page,
                page_rect=page_rect,
                caption_rect=caption_rect,
                title_rect=caption_rect.adjusted(8.0, 3.0, -8.0, -caption_height / 2.0),
                summary_rect=caption_rect.adjusted(8.0, caption_height / 2.0 - 2.0, -8.0, -3.0),
            )
        ]

    def _facing_layout(self, state: PreviewState, available: QtCore.QRectF) -> list[_LayoutEntry]:
        pages = state.pages
        if len(pages) < 2:
            return self._single_layout(state, available)

        left_page, right_page = pages[0], pages[1]
        caption_height = 48.0
        gap = 28.0
        page_band_height = max(1.0, available.height() - caption_height - 6.0)

        left_size = self._page_size(left_page)
        right_size = self._page_size(right_page)
        scale_width = (available.width() - gap) / (left_size[0] + right_size[0])
        scale_height = page_band_height / max(left_size[1], right_size[1])
        scale = max(min(scale_width, scale_height), 0.01)

        left_draw = (left_size[0] * scale, left_size[1] * scale)
        right_draw = (right_size[0] * scale, right_size[1] * scale)
        total_width = left_draw[0] + gap + right_draw[0]
        start_x = available.left() + (available.width() - total_width) / 2.0
        band_top = available.top() + (page_band_height - max(left_draw[1], right_draw[1])) / 2.0
        caption_top = band_top + max(left_draw[1], right_draw[1]) + 6.0

        left_rect = QtCore.QRectF(start_x, band_top + (max(left_draw[1], right_draw[1]) - left_draw[1]) / 2.0, left_draw[0], left_draw[1])
        right_rect = QtCore.QRectF(left_rect.right() + gap, band_top + (max(left_draw[1], right_draw[1]) - right_draw[1]) / 2.0, right_draw[0], right_draw[1])

        left_caption = QtCore.QRectF(left_rect.left(), caption_top, left_rect.width(), caption_height)
        right_caption = QtCore.QRectF(right_rect.left(), caption_top, right_rect.width(), caption_height)
        return [
            _LayoutEntry(
                page=left_page,
                page_rect=left_rect,
                caption_rect=left_caption,
                title_rect=left_caption.adjusted(8.0, 3.0, -8.0, -caption_height / 2.0),
                summary_rect=left_caption.adjusted(8.0, caption_height / 2.0 - 1.0, -8.0, -3.0),
            ),
            _LayoutEntry(
                page=right_page,
                page_rect=right_rect,
                caption_rect=right_caption,
                title_rect=right_caption.adjusted(8.0, 3.0, -8.0, -caption_height / 2.0),
                summary_rect=right_caption.adjusted(8.0, caption_height / 2.0 - 1.0, -8.0, -3.0),
            ),
        ]

    @staticmethod
    def _page_size(page: PreviewPage) -> tuple[float, float]:
        return page.page_rect.width, page.page_rect.height

    @staticmethod
    def _map_source_rect(source_rect: fitz.Rect, widget_rect: QtCore.QRectF, rect: fitz.Rect) -> QtCore.QRectF:
        scale_x = widget_rect.width() / source_rect.width
        scale_y = widget_rect.height() / source_rect.height
        left = widget_rect.left() + (rect.x0 - source_rect.x0) * scale_x
        top = widget_rect.top() + (rect.y0 - source_rect.y0) * scale_y
        return QtCore.QRectF(left, top, rect.width * scale_x, rect.height * scale_y)

    @staticmethod
    def _pixmap_to_qpixmap(pixmap: fitz.Pixmap) -> QtGui.QPixmap:
        image = QtGui.QImage(
            pixmap.samples,
            pixmap.width,
            pixmap.height,
            pixmap.stride,
            QtGui.QImage.Format.Format_RGB888,
        )
        return QtGui.QPixmap.fromImage(image.copy())
