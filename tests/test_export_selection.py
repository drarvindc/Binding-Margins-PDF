from pathlib import Path

from book_gutter.document_layout import DocumentLayout, OutputItem, OutputItemKind
from book_gutter.export_selection import (
    ExportSelection,
    current_page_pair_selection,
    custom_page_range_selection,
    suggest_test_export_filename,
)
from book_gutter.page_side import PageSide
from book_gutter.pdf_transform import ShiftSettings


def _make_composition(page_count: int = 8, layout: DocumentLayout | None = None):
    layout = layout or DocumentLayout()
    return layout.compose([(200.0, 300.0)] * page_count)


def test_current_page_1_resolves_to_source_pages_1_3():
    composition = _make_composition(8)
    selection = current_page_pair_selection(1, composition)
    assert selection.source_page_numbers == (1, 2, 3)
    assert selection.selected_spread_source_page_numbers == (1, 2)
    assert selection.blank_page_count == 1


def test_current_page_3_resolves_to_source_pages_1_4():
    composition = _make_composition(8)
    selection = current_page_pair_selection(3, composition)
    assert selection.source_page_numbers == (1, 2, 3, 4)
    assert selection.selected_spread_source_page_numbers == (2, 3)
    assert selection.blank_page_count == 0


def test_current_page_15_resolves_to_source_pages_13_15():
    composition = _make_composition(15)
    selection = current_page_pair_selection(15, composition)
    assert selection.source_page_numbers == (13, 14, 15)
    assert selection.selected_spread_source_page_numbers == (14, 15)
    assert selection.blank_page_count == 1


def test_custom_range_2_to_5_expands_to_1_to_6():
    composition = _make_composition(8)
    selection, warning = custom_page_range_selection(2, 5, composition, True)
    assert selection.source_page_numbers == (1, 2, 3, 4, 5, 6)
    assert selection.blank_page_count == 0
    assert warning is not None


def test_custom_range_with_intentional_blank_includes_it():
    composition = _make_composition(6, DocumentLayout().add_blank_before(3))
    selection, warning = custom_page_range_selection(2, 4, composition, False)
    assert warning is not None
    assert selection.source_page_numbers == (2, 3, 4)
    assert selection.intentional_blank_count == 1
    assert selection.blank_page_count == 1


def test_custom_range_4_to_4_expands_to_3_to_4():
    composition = _make_composition(8)
    selection, warning = custom_page_range_selection(4, 4, composition, True)
    assert selection.source_page_numbers == (3, 4)
    assert selection.blank_page_count == 0
    assert warning is not None


def test_test_filename_uses_selected_spread_for_quick_test():
    composition = _make_composition(8)
    selection = current_page_pair_selection(3, composition)
    assert suggest_test_export_filename(Path("Book.pdf"), selection, ShiftSettings(7.0, 10.0), 100.0) == "Book_TEST_SPREAD_2-3_O7mm_E10mm_100pct.pdf"


def test_test_filename_marks_intentional_blanks_when_present():
    selection = ExportSelection(
        kind="custom",
        items=(
            OutputItem(kind=OutputItemKind.SOURCE_PAGE, output_position=1, side=PageSide.RIGHT_ODD, page_width_pt=200.0, page_height_pt=300.0, source_page_index=9, source_page_number=10),
            OutputItem(kind=OutputItemKind.INTENTIONAL_BLANK, output_position=2, side=PageSide.LEFT_EVEN, page_width_pt=200.0, page_height_pt=300.0, blank_reference_source_page_number=10),
            OutputItem(kind=OutputItemKind.SOURCE_PAGE, output_position=3, side=PageSide.RIGHT_ODD, page_width_pt=200.0, page_height_pt=300.0, source_page_index=10, source_page_number=11),
        ),
        source_page_numbers=(10, 11),
        selected_spread_source_page_numbers=(10, 11),
        description="Custom range 10-11",
        intentional_blank_count=1,
        test_padding_blank_count=0,
    )
    assert suggest_test_export_filename(Path("Book.pdf"), selection, ShiftSettings(7.0, 10.0), 100.0) == "Book_TEST_PAGES_10-BLANK-11_O7mm_E10mm_100pct.pdf"
