import fitz

from book_gutter.pdf_transform import BindingSide, page_shift_sign, target_rect_for_page


def test_shift_left_binding_odd_even():
    assert page_shift_sign(0, BindingSide.LEFT) == 1
    assert page_shift_sign(1, BindingSide.LEFT) == -1


def test_shift_right_binding_odd_even():
    assert page_shift_sign(0, BindingSide.RIGHT) == -1
    assert page_shift_sign(1, BindingSide.RIGHT) == 1


def test_centered_scale_and_shift():
    rect = fitz.Rect(0, 0, 210, 297)
    target = target_rect_for_page(rect, 95.0, 5.0, 0, BindingSide.LEFT)
    assert abs(target.width - rect.width * 0.95) < 1e-6
    assert abs(target.height - rect.height * 0.95) < 1e-6
