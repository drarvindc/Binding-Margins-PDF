import pytest
import fitz

from book_gutter.document_layout import DocumentLayout
from book_gutter.page_side import PageSide
from book_gutter.pdf_transform import BindingSide, ShiftSettings, placement_for_page
from book_gutter.preview_widget import preview_overlay_rects
from book_gutter.units import mm_to_points


def _overlay_for(page_side: PageSide, scale: float, odd_mm: float, even_mm: float, binding_side: BindingSide) -> tuple[fitz.Rect, fitz.Rect]:
    page_rect = fitz.Rect(0, 0, 200, 300)
    placement = placement_for_page(page_rect, scale, ShiftSettings(odd_mm, even_mm), page_side, binding_side)
    overlay = preview_overlay_rects(page_rect, placement.target_rect)
    return overlay.current_rect, overlay.original_rect


def test_preview_overlay_rects_distinguish_original_and_current_geometry():
    current, original = _overlay_for(PageSide.RIGHT_ODD, 100.0, 15.0, 15.0, BindingSide.LEFT)
    assert current != original
    assert current.x0 - original.x0 == pytest.approx(mm_to_points(15.0))


def test_left_binding_moves_right_odd_pages_right_and_left_even_pages_left():
    current, original = _overlay_for(PageSide.RIGHT_ODD, 100.0, 15.0, 10.0, BindingSide.LEFT)
    assert current.x0 > original.x0
    assert current.x0 - original.x0 == pytest.approx(mm_to_points(15.0))

    current, original = _overlay_for(PageSide.LEFT_EVEN, 100.0, 15.0, 10.0, BindingSide.LEFT)
    assert current.x0 < original.x0
    assert original.x0 - current.x0 == pytest.approx(mm_to_points(10.0))


def test_right_binding_reverses_shift_direction():
    current, original = _overlay_for(PageSide.RIGHT_ODD, 100.0, 15.0, 10.0, BindingSide.RIGHT)
    assert current.x0 < original.x0
    assert original.x0 - current.x0 == pytest.approx(mm_to_points(15.0))

    current, original = _overlay_for(PageSide.LEFT_EVEN, 100.0, 15.0, 10.0, BindingSide.RIGHT)
    assert current.x0 > original.x0
    assert current.x0 - original.x0 == pytest.approx(mm_to_points(10.0))


def test_reduced_scale_keeps_original_rect_centered_before_shift():
    page_rect = fitz.Rect(0, 0, 200, 300)
    placement = placement_for_page(page_rect, 80.0, ShiftSettings(15.0, 15.0), PageSide.RIGHT_ODD, BindingSide.LEFT)
    overlay = preview_overlay_rects(page_rect, placement.target_rect)

    assert overlay.current_rect.width < page_rect.width
    assert overlay.original_rect.width == pytest.approx(overlay.current_rect.width)
    original_center_x = (overlay.original_rect.x0 + overlay.original_rect.x1) / 2.0
    current_center_x = (overlay.current_rect.x0 + overlay.current_rect.x1) / 2.0
    page_center_x = (page_rect.x0 + page_rect.x1) / 2.0
    assert original_center_x == pytest.approx(page_center_x)
    assert current_center_x - original_center_x == pytest.approx(mm_to_points(15.0))


def test_facing_pages_use_independent_overlay_rects_for_each_side():
    page_rect = fitz.Rect(0, 0, 200, 300)
    odd_placement = placement_for_page(page_rect, 100.0, ShiftSettings(15.0, 5.0), PageSide.RIGHT_ODD, BindingSide.LEFT)
    even_placement = placement_for_page(page_rect, 100.0, ShiftSettings(15.0, 5.0), PageSide.LEFT_EVEN, BindingSide.LEFT)

    odd_overlay = preview_overlay_rects(page_rect, odd_placement.target_rect)
    even_overlay = preview_overlay_rects(page_rect, even_placement.target_rect)

    assert odd_overlay.current_rect.x0 - odd_overlay.original_rect.x0 == pytest.approx(mm_to_points(15.0))
    assert even_overlay.original_rect.x0 - even_overlay.current_rect.x0 == pytest.approx(mm_to_points(5.0))
    assert odd_overlay.current_rect.x0 - odd_overlay.original_rect.x0 != pytest.approx(
        even_overlay.original_rect.x0 - even_overlay.current_rect.x0
    )
