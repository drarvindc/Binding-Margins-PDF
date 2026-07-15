import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6 import QtCore, QtTest

from book_gutter.main_window import MainWindow


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


def test_preview_mode_switch_preserves_active_page(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.page_spin.setValue(4)
    window.preview_mode_combo.setCurrentIndex(1)
    qapp.processEvents()
    assert window.page_spin.value() == 4

    window.preview_mode_combo.setCurrentIndex(0)
    qapp.processEvents()
    assert window.page_spin.value() == 4
    window.close()


def test_facing_preview_clicks_pages_and_ignores_placeholder(tmp_path, qapp):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    window = MainWindow()
    window.load_pdf(src)
    _show_window(window, qapp)

    window.preview_mode_combo.setCurrentIndex(1)
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
