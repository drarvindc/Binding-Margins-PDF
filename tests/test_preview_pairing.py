from book_gutter.document_layout import DocumentLayout
from book_gutter.preview_pairing import format_facing_indicator, next_output_position, previous_output_position, resolve_facing_spread


def test_cover_and_pair_spreads_are_resolved_correctly():
    composition = DocumentLayout().compose([(200.0, 300.0)] * 5)
    cover = resolve_facing_spread(composition, 1)
    assert cover.left_item is None
    assert cover.right_item.source_page_number == 1
    assert format_facing_indicator(cover) == "Output 1 with left placeholder"

    pair = resolve_facing_spread(composition, 2)
    assert pair.left_item.source_page_number == 2
    assert pair.right_item.source_page_number == 3
    assert format_facing_indicator(pair) == "Output 2-3"

    same_pair = resolve_facing_spread(composition, 3)
    assert same_pair.left_item.source_page_number == 2
    assert same_pair.right_item.source_page_number == 3


def test_final_spread_handles_right_placeholder():
    composition = DocumentLayout().compose([(200.0, 300.0)] * 1)
    spread = resolve_facing_spread(composition, 1)
    assert spread.left_item is None
    assert spread.right_item.source_page_number == 1
    assert format_facing_indicator(spread) == "Output 1 with left placeholder"


def test_navigation_moves_through_output_sequence():
    assert next_output_position(1, 5) == 2
    assert next_output_position(2, 5) == 3
    assert next_output_position(5, 5) == 5

    assert previous_output_position(1, 5) == 1
    assert previous_output_position(2, 5) == 1
    assert previous_output_position(4, 5) == 3
