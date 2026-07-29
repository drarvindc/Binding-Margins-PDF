import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6 import QtCore, QtTest

from book_gutter.main_window import MainWindow
from book_gutter.preview_widget import PreviewMode


def make_pdf(path: Path, page_count: int = 5) -> None:
    doc = fitz.open()
    for index in range(page_count):
        page = doc.new_page(width=220, height=300)
        page.insert_text((40, 40), f"Page {index + 1}")
    doc.save(path)
    doc.close()


def _show_window(window: MainWindow, qapp) -> None:
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()


def test_first_page_side_setting_flips_preview_labels(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.page_spin.setValue(1)
    qapp.processEvents()
    assert "Computed side: Right / Odd" in window.side_label.text()
    assert "Current item: Source page 1" in window.current_item_label.text()

    window.first_page_side_combo.setCurrentIndex(1)
    qapp.processEvents()
    assert "Computed side: Left / Even" in window.side_label.text()
    assert "Current item: Source page 1" in window.current_item_label.text()
    window.close()


def test_preview_mode_switch_preserves_active_page(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.page_spin.setValue(4)
    window.preview_mode_facing_button.click()
    qapp.processEvents()
    assert window.page_spin.value() == 4
    assert window.preview._state is not None
    assert window.preview._state.mode == PreviewMode.FACING_PAGES

    window.preview_mode_single_button.click()
    qapp.processEvents()
    assert window.page_spin.value() == 4
    assert window.preview._state is not None
    assert window.preview._state.mode == PreviewMode.SINGLE_PAGE
    window.close()


def test_facing_preview_clicks_pages_and_ignores_placeholder(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.preview_mode_facing_button.click()
    window.page_spin.setValue(3)
    qapp.processEvents()

    regions = window.preview.hit_regions()
    left_region = next(region.rect for region in regions if region.page_number == 2)
    right_region = next(region.rect for region in regions if region.page_number == 3)

    QtTest.QTest.mouseClick(
        window.preview,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        left_region.center().toPoint(),
    )
    qapp.processEvents()
    assert window.page_spin.value() == 2

    regions = window.preview.hit_regions()
    right_region = next(region.rect for region in regions if region.page_number == 3)
    QtTest.QTest.mouseClick(
        window.preview,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        right_region.center().toPoint(),
    )
    qapp.processEvents()
    assert window.page_spin.value() == 3

    window.page_spin.setValue(1)
    qapp.processEvents()
    regions = window.preview.hit_regions()
    placeholder_region = next(region.rect for region in regions if region.is_placeholder)
    QtTest.QTest.mouseClick(
        window.preview,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        placeholder_region.center().toPoint(),
    )
    qapp.processEvents()
    assert window.page_spin.value() == 1
    window.close()


def test_preview_header_buttons_and_labels_are_concise(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    assert window.preview_mode_single_button.text() == "Single Page"
    assert window.preview_mode_facing_button.text() == "Facing Pages"
    assert window.preview_mode_single_button.isChecked() is True
    assert window.preview_mode_facing_button.isChecked() is False
    assert window.preview._state is not None
    assert window.preview._state.indicator_text == ""

    window.page_spin.setValue(2)
    qapp.processEvents()
    assert window.preview._state.pages[0].title_text == "Source page 2 — Left / Even"
    assert "Output" not in window.preview._state.pages[0].title_text

    window.page_spin.setValue(2)
    window.insert_blank_before_current_page()
    qapp.processEvents()
    window._set_active_output_position(2)
    qapp.processEvents()
    assert window.preview._state.pages[0].title_text == "Inserted blank — Left / Even"
    assert "Output" not in window.preview._state.pages[0].title_text
    window.close()


def test_preview_footer_controls_replace_instruction_text(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    assert window.prev_button.text() == "Previous"
    assert window.next_button.text() == "Next"
    assert window.preview_location_label.text() == "Page 1 of 5"
    assert "Click a visible page" not in window.preview_location_label.text()
    assert "Full export" not in window.preview_location_label.text()
    window.close()


def test_preview_footer_navigation_updates_pages_and_spreads(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.page_spin.setValue(2)
    qapp.processEvents()
    window.next_button.click()
    qapp.processEvents()
    assert window.page_spin.value() == 3
    assert window.preview_location_label.text() == "Page 3 of 5"

    window.preview_mode_facing_button.click()
    qapp.processEvents()
    window.page_spin.setValue(2)
    qapp.processEvents()
    assert window.preview_location_label.text() == "Pages 2-3 of 5"

    window.next_button.click()
    qapp.processEvents()
    assert window.preview_location_label.text() == "Pages 2-3 of 5"

    window.next_button.click()
    qapp.processEvents()
    assert window.preview_location_label.text() == "Pages 4-5 of 5"
    window.close()
