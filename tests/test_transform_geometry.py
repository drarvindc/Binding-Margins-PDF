from pathlib import Path

import fitz

from book_gutter.export_selection import suggest_full_export_filename
from book_gutter.pdf_transform import BindingSide, ShiftSettings, page_shift_sign, placement_for_page, target_rect_for_page


def test_odd_source_page_uses_odd_shift_value():
    rect = fitz.Rect(0, 0, 210, 297)
    placement = placement_for_page(rect, 100.0, ShiftSettings(11.0, 15.0), 0, BindingSide.LEFT)
    assert placement.shift_mm == 11.0


def test_even_source_page_uses_even_shift_value():
    rect = fitz.Rect(0, 0, 210, 297)
    placement = placement_for_page(rect, 100.0, ShiftSettings(11.0, 15.0), 1, BindingSide.LEFT)
    assert placement.shift_mm == 15.0


def test_left_binding_directions_remain_correct():
    assert page_shift_sign(0, BindingSide.LEFT) == 1
    assert page_shift_sign(1, BindingSide.LEFT) == -1


def test_right_binding_directions_remain_correct():
    assert page_shift_sign(0, BindingSide.RIGHT) == -1
    assert page_shift_sign(1, BindingSide.RIGHT) == 1


def test_equal_shift_mode_keeps_values_synchronized():
    shifts = ShiftSettings(5.0, 5.0)
    assert shifts.is_uniform() is True
    assert shifts.mm_for_page(0) == 5.0
    assert shifts.mm_for_page(1) == 5.0


def test_unequal_shifts_are_passed_into_geometry():
    rect = fitz.Rect(0, 0, 210, 297)
    left_page = placement_for_page(rect, 100.0, ShiftSettings(11.0, 15.0), 0, BindingSide.LEFT)
    right_page = placement_for_page(rect, 100.0, ShiftSettings(11.0, 15.0), 1, BindingSide.LEFT)
    assert left_page.shift_mm == 11.0
    assert right_page.shift_mm == 15.0
    assert left_page.target_rect.x0 > right_page.target_rect.x0


def test_filename_generation_for_equal_shifts():
    assert suggest_full_export_filename(Path("Book.pdf"), ShiftSettings(5.0, 5.0), 100.0) == "Book_GUTTER_5mm_100pct.pdf"


def test_filename_generation_for_unequal_shifts():
    assert suggest_full_export_filename(Path("Book.pdf"), ShiftSettings(11.0, 15.0), 100.0) == "Book_GUTTER_O11mm_E15mm_100pct.pdf"


def test_centered_scale_preserves_source_width_and_height():
    rect = fitz.Rect(0, 0, 210, 297)
    target = target_rect_for_page(rect, 100.0, 5.0, 0, BindingSide.LEFT)
    assert target.width == rect.width
    assert target.height == rect.height


def test_reduced_scale_stays_centered_before_shift():
    rect = fitz.Rect(0, 0, 210, 297)
    target = target_rect_for_page(rect, 90.0, 0.0, 0, BindingSide.LEFT)
    assert abs(target.x0 + target.x1 - rect.x0 - rect.x1) < 1e-6
    assert abs(target.y0 + target.y1 - rect.y0 - rect.y1) < 1e-6
