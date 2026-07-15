from book_gutter.document_layout import BlankPlacement, DocumentLayout, OutputItemKind
from book_gutter.page_side import PageSide


def _compose(layout: DocumentLayout, page_count: int = 4):
    return layout.compose([(200.0, 300.0), (220.0, 320.0), (240.0, 340.0), (260.0, 360.0)][:page_count])


def test_default_first_page_side_is_right_odd():
    composition = _compose(DocumentLayout())
    source_items = [item for item in composition.items if item.kind == OutputItemKind.SOURCE_PAGE]
    assert [item.side for item in source_items] == [PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD, PageSide.LEFT_EVEN]


def test_left_even_setting_flips_source_sides():
    composition = _compose(DocumentLayout(first_page_side=PageSide.LEFT_EVEN))
    source_items = [item for item in composition.items if item.kind == OutputItemKind.SOURCE_PAGE]
    assert [item.side for item in source_items] == [PageSide.LEFT_EVEN, PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD]


def test_blank_before_source_page_flips_following_sides():
    layout = DocumentLayout().add_blank_before(3)
    composition = _compose(layout)
    sides = [item.side for item in composition.items]
    assert sides == [PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD]
    blank = next(item for item in composition.items if item.kind == OutputItemKind.INTENTIONAL_BLANK)
    assert blank.blank_placement == BlankPlacement.BEFORE
    assert blank.blank_reference_source_page_number == 3


def test_blank_after_source_page_flips_later_sides_only():
    layout = DocumentLayout().add_blank_after(2)
    composition = _compose(layout)
    sides = [item.side for item in composition.items]
    assert sides == [PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD, PageSide.LEFT_EVEN, PageSide.RIGHT_ODD]
    blank = next(item for item in composition.items if item.kind == OutputItemKind.INTENTIONAL_BLANK)
    assert blank.blank_placement == BlankPlacement.AFTER
    assert blank.blank_reference_source_page_number == 2


def test_blank_dimensions_match_the_reference_page():
    before_layout = DocumentLayout().add_blank_before(2)
    before_composition = _compose(before_layout)
    before_blank = next(item for item in before_composition.items if item.kind == OutputItemKind.INTENTIONAL_BLANK)
    assert before_blank.page_width_pt == 220.0
    assert before_blank.page_height_pt == 320.0

    after_layout = DocumentLayout().add_blank_after(2)
    after_composition = _compose(after_layout)
    after_blank = next(item for item in after_composition.items if item.kind == OutputItemKind.INTENTIONAL_BLANK)
    assert after_blank.page_width_pt == 220.0
    assert after_blank.page_height_pt == 320.0


def test_removing_a_blank_restores_parity():
    layout = DocumentLayout().add_blank_before(3)
    blank_id = layout.intentional_blanks[0].insertion_id
    restored = layout.remove_blank(blank_id)
    original = _compose(DocumentLayout())
    restored_composition = _compose(restored)
    assert [item.side for item in restored_composition.items if item.kind == OutputItemKind.SOURCE_PAGE] == [item.side for item in original.items if item.kind == OutputItemKind.SOURCE_PAGE]


def test_clear_blanks_resets_document_layout():
    layout = DocumentLayout().add_blank_before(2).add_blank_after(3)
    cleared = layout.clear_blanks()
    assert cleared.intentional_blanks == ()
    assert cleared.first_page_side == PageSide.RIGHT_ODD


def test_reset_for_new_document_clears_blanks_and_restores_default_side():
    layout = DocumentLayout(first_page_side=PageSide.LEFT_EVEN).add_blank_before(2)
    reset = layout.reset_for_new_document()
    assert reset.first_page_side == PageSide.RIGHT_ODD
    assert reset.intentional_blanks == ()
