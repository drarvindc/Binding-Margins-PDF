from book_gutter.preview_pairing import (
    facing_final_spread_start,
    format_facing_indicator,
    next_facing_page_number,
    previous_facing_page_number,
    resolve_facing_spread,
)


def test_cover_and_pair_spreads_are_resolved_correctly():
    cover = resolve_facing_spread(1, 5)
    assert cover.left_page_number is None
    assert cover.right_page_number == 1
    assert format_facing_indicator(cover, 5) == "Page 1 of 5"

    pair = resolve_facing_spread(2, 5)
    assert pair.left_page_number == 2
    assert pair.right_page_number == 3
    assert format_facing_indicator(pair, 5) == "Pages 2-3 of 5"

    same_pair = resolve_facing_spread(3, 5)
    assert same_pair.left_page_number == 2
    assert same_pair.right_page_number == 3


def test_final_spread_handles_blank_right_placeholder():
    spread = resolve_facing_spread(4, 4)
    assert spread.left_page_number == 4
    assert spread.right_page_number is None
    assert format_facing_indicator(spread, 4) == "Page 4 of 4 with right placeholder"
    assert facing_final_spread_start(4) == 4
    assert facing_final_spread_start(5) == 4


def test_facing_navigation_moves_by_spread():
    assert next_facing_page_number(1, 5) == 2
    assert next_facing_page_number(2, 5) == 4
    assert next_facing_page_number(3, 5) == 4
    assert next_facing_page_number(5, 5) == 4

    assert previous_facing_page_number(1, 5) == 1
    assert previous_facing_page_number(2, 5) == 1
    assert previous_facing_page_number(3, 5) == 1
    assert previous_facing_page_number(4, 5) == 2
