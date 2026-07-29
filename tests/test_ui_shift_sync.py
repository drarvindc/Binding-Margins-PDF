import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz

from book_gutter.main_window import MainWindow


def make_pdf(path: Path) -> None:
    doc = fitz.open()
    for i in range(2):
        page = doc.new_page(width=200, height=300)
        page.insert_text((40, 40), f"Page {i + 1}")
    doc.save(path)
    doc.close()


def test_equal_shift_mode_keeps_values_synchronized(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    window.same_shift_check.setChecked(True)
    window.odd_shift_spin.setValue(7.5)
    assert window.even_shift_spin.value() == 7.5
    assert window.even_shift_spin.isEnabled() is False
    window.close()


def test_unequal_shifts_are_passed_into_preview_geometry(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    window.first_page_side_combo.setCurrentIndex(1)
    window.same_shift_check.setChecked(False)
    window.odd_shift_spin.setValue(11.0)
    window.even_shift_spin.setValue(15.0)

    window.page_spin.setValue(1)
    window.refresh_preview()
    odd_state = window.preview._state
    assert odd_state is not None
    odd_page = odd_state.pages[0]
    assert odd_page.page_side is not None
    assert odd_page.page_side.label == "Left / Even"
    assert odd_page.target_rect.x0 < odd_page.page_rect.x0

    window.page_spin.setValue(2)
    window.refresh_preview()
    even_state = window.preview._state
    assert even_state is not None
    even_page = even_state.pages[1]
    assert even_page.page_side is not None
    assert even_page.page_side.label == "Right / Odd"
    assert even_page.target_rect.x0 > even_page.page_rect.x0
    window.close()
