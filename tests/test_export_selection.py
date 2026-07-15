from book_gutter.export_selection import current_page_pair_selection, custom_page_range_selection


def test_current_page_1_resolves_to_source_pages_1_2():
    selection = current_page_pair_selection(1, 8)
    assert selection.source_page_numbers == (1, 2)
    assert selection.append_blank_partner is False


def test_current_page_2_resolves_to_source_pages_1_2():
    selection = current_page_pair_selection(2, 8)
    assert selection.source_page_numbers == (1, 2)
    assert selection.append_blank_partner is False


def test_current_page_7_resolves_to_source_pages_7_8():
    selection = current_page_pair_selection(7, 8)
    assert selection.source_page_numbers == (7, 8)
    assert selection.append_blank_partner is False


def test_custom_range_2_to_5_expands_to_1_to_6():
    selection, warning = custom_page_range_selection(2, 5, 8, True)
    assert selection.source_page_numbers == (1, 2, 3, 4, 5, 6)
    assert selection.append_blank_partner is False
    assert warning is not None


def test_custom_range_4_to_4_expands_to_3_to_4():
    selection, warning = custom_page_range_selection(4, 4, 8, True)
    assert selection.source_page_numbers == (3, 4)
    assert selection.append_blank_partner is False
    assert warning is not None
