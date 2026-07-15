from pathlib import Path

from book_gutter.export_selection import current_page_pair_selection, custom_page_range_selection, suggest_test_export_filename
from book_gutter.pdf_transform import ShiftSettings


def test_current_page_1_resolves_to_source_pages_1_4():
    selection = current_page_pair_selection(1, 8)
    assert selection.source_page_numbers == (1, 2, 3, 4)
    assert selection.append_blank_partner is False
    assert selection.blank_page_count == 0


def test_current_page_2_resolves_to_source_pages_1_4():
    selection = current_page_pair_selection(2, 8)
    assert selection.source_page_numbers == (1, 2, 3, 4)
    assert selection.append_blank_partner is False
    assert selection.blank_page_count == 0


def test_current_page_7_resolves_to_source_pages_7_10():
    selection = current_page_pair_selection(7, 12)
    assert selection.source_page_numbers == (7, 8, 9, 10)
    assert selection.append_blank_partner is False
    assert selection.blank_page_count == 0


def test_custom_range_2_to_5_expands_to_1_to_6():
    selection, warning = custom_page_range_selection(2, 5, 8, True)
    assert selection.source_page_numbers == (1, 2, 3, 4, 5, 6)
    assert selection.append_blank_partner is False
    assert selection.blank_page_count == 0
    assert warning is not None


def test_custom_range_4_to_4_expands_to_3_to_4():
    selection, warning = custom_page_range_selection(4, 4, 8, True)
    assert selection.source_page_numbers == (3, 4)
    assert selection.append_blank_partner is False
    assert selection.blank_page_count == 0
    assert warning is not None


def test_test_filename_uses_source_range_for_quick_test():
    selection = current_page_pair_selection(3, 6)
    assert suggest_test_export_filename(Path("Book.pdf"), selection, ShiftSettings(7.0, 10.0), 100.0) == "Book_TEST_PAGES_3-6_O7mm_E10mm_100pct.pdf"


def test_test_filename_keeps_source_range_when_blanks_are_appended():
    selection = current_page_pair_selection(15, 15)
    assert suggest_test_export_filename(Path("Book.pdf"), selection, ShiftSettings(7.0, 10.0), 100.0) == "Book_TEST_PAGES_13-15_O7mm_E10mm_100pct.pdf"
