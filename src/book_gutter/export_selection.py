from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .document_layout import DocumentComposition, DocumentLayout, OutputItem, OutputItemKind
from .page_side import PageSide
from .pdf_transform import ShiftSettings
from .units import format_compact_number, format_mm_compact


@dataclass(frozen=True)
class ExportSelection:
    kind: str
    items: tuple[OutputItem, ...]
    source_page_numbers: tuple[int, ...]
    selected_spread_source_page_numbers: tuple[int | None, int | None]
    description: str
    intentional_blank_count: int = 0
    test_padding_blank_count: int = 0

    @property
    def page_indices(self) -> tuple[int, ...]:
        return tuple(page_number - 1 for page_number in self.source_page_numbers)

    @property
    def blank_page_count(self) -> int:
        return self.intentional_blank_count + self.test_padding_blank_count

    @property
    def append_blank_partner(self) -> bool:
        return self.test_padding_blank_count > 0


def _validate_range(start_page: int, end_page: int, page_count: int) -> None:
    if page_count <= 0:
        raise ValueError("The source document has no pages.")
    if start_page < 1 or end_page < 1:
        raise ValueError("Page numbers must be 1 or higher.")
    if start_page > page_count or end_page > page_count:
        raise ValueError("The selected page range must be within the source document.")
    if start_page > end_page:
        raise ValueError("The start page must not be after the end page.")


def _compose_document(composition: DocumentComposition, start_position: int, end_position: int) -> tuple[OutputItem, ...]:
    return tuple(composition.items[start_position - 1 : end_position])


def _clone_item(item: OutputItem, output_position: int) -> OutputItem:
    return OutputItem(
        kind=item.kind,
        output_position=output_position,
        side=item.side,
        page_width_pt=item.page_width_pt,
        page_height_pt=item.page_height_pt,
        source_page_index=item.source_page_index,
        source_page_number=item.source_page_number,
        blank_insertion_id=item.blank_insertion_id,
        blank_reference_source_page_number=item.blank_reference_source_page_number,
        blank_placement=item.blank_placement,
    )


def _clone_padding_blank(reference: OutputItem, output_position: int, first_page_side: PageSide) -> OutputItem:
    return OutputItem(
        kind=OutputItemKind.TEST_PADDING_BLANK,
        output_position=output_position,
        side=DocumentLayout.side_for_output_position(output_position, first_page_side),
        page_width_pt=reference.page_width_pt,
        page_height_pt=reference.page_height_pt,
    )


def _selected_source_numbers(items: tuple[OutputItem, ...]) -> tuple[int, ...]:
    return tuple(item.source_page_number for item in items if item.kind == OutputItemKind.SOURCE_PAGE and item.source_page_number is not None)


def _intentional_blank_count(items: tuple[OutputItem, ...]) -> int:
    return sum(1 for item in items if item.kind == OutputItemKind.INTENTIONAL_BLANK)


def _find_source_item(composition: DocumentComposition, source_page_number: int) -> OutputItem:
    item = composition.source_item(source_page_number)
    if item is None:
        raise ValueError("The selected page range must be within the source document.")
    return item


def _selected_spread_positions(composition: DocumentComposition, current_source_page: int) -> tuple[int, int]:
    current = _find_source_item(composition, current_source_page)
    previous_item = composition.item_at_output_position(current.output_position - 1) if current.output_position > 1 else None
    next_item = composition.item_at_output_position(current.output_position + 1) if current.output_position < len(composition.items) else None

    if current.side == PageSide.RIGHT_ODD:
        if previous_item is not None:
            return previous_item.output_position, current.output_position
        if next_item is not None:
            return current.output_position, next_item.output_position
        return current.output_position, current.output_position

    if next_item is not None:
        return current.output_position, next_item.output_position
    if previous_item is not None:
        return previous_item.output_position, current.output_position
    return current.output_position, current.output_position


def _padding_pair_for_boundary(
    composition: DocumentComposition,
    current_item: OutputItem,
    output_position: int,
    use_leading_blank: bool,
) -> tuple[OutputItem, OutputItem]:
    blank_position = output_position - 1 if use_leading_blank else output_position + 1
    blank = _clone_padding_blank(current_item, blank_position, composition.first_page_side)
    if use_leading_blank:
        return blank, current_item
    return current_item, blank


def current_page_pair_selection(current_page: int, composition: DocumentComposition) -> ExportSelection:
    current = _find_source_item(composition, current_page)
    pair_start, pair_end = _selected_spread_positions(composition, current_page)
    if pair_start == pair_end:
        if current.side == PageSide.RIGHT_ODD:
            if current.output_position > 1:
                previous_item = composition.item_at_output_position(current.output_position - 1)
                if previous_item.side == PageSide.LEFT_EVEN:
                    selected_pair = (
                        _clone_item(previous_item, 2),
                        _clone_item(current, 3),
                    )
                else:
                    selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=True)
            elif current.output_position < len(composition.items):
                next_item = composition.item_at_output_position(current.output_position + 1)
                if next_item.side == PageSide.LEFT_EVEN:
                    selected_pair = (
                        _clone_item(current, 2),
                        _clone_item(next_item, 3),
                    )
                else:
                    selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=True)
            else:
                selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=True)
        else:
            if current.output_position < len(composition.items):
                next_item = composition.item_at_output_position(current.output_position + 1)
                if next_item.side == PageSide.RIGHT_ODD:
                    selected_pair = (
                        _clone_item(current, 2),
                        _clone_item(next_item, 3),
                    )
                else:
                    selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=False)
            elif current.output_position > 1:
                previous_item = composition.item_at_output_position(current.output_position - 1)
                if previous_item.side == PageSide.RIGHT_ODD:
                    selected_pair = (
                        _clone_item(previous_item, 2),
                        _clone_item(current, 3),
                    )
                else:
                    selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=False)
            else:
                selected_pair = _padding_pair_for_boundary(composition, current, 2, use_leading_blank=False)
    else:
        selected_pair = tuple(
            _clone_item(composition.item_at_output_position(position), output_position=index)
            for index, position in enumerate(range(pair_start, pair_end + 1), start=2)
        )

    preceding = composition.item_at_output_position(pair_start - 1) if pair_start > 1 else None
    following = composition.item_at_output_position(pair_end + 1) if pair_end < len(composition.items) else None

    items: list[OutputItem] = []
    if preceding is None:
        padding_reference = selected_pair[0]
        items.append(_clone_padding_blank(padding_reference, 1, composition.first_page_side))
    else:
        items.append(_clone_item(preceding, 1))

    if selected_pair:
        items.extend(selected_pair)

    if following is None:
        padding_reference = selected_pair[-1]
        items.append(_clone_padding_blank(padding_reference, 4, composition.first_page_side))
    else:
        items.append(_clone_item(following, 4))

    if len(items) < 4:
        while len(items) < 4:
            items.append(_clone_padding_blank(items[-1], len(items) + 1, composition.first_page_side))
    elif len(items) > 4:
        items = items[:4]

    source_page_numbers = _selected_source_numbers(tuple(items))
    spread_source_page_numbers = tuple(
        item.source_page_number if item.kind == OutputItemKind.SOURCE_PAGE else None
        for item in selected_pair
    )
    description = f"Two duplex sheets - selected spread {suggested_spread_text(spread_source_page_numbers)}"
    intentional_blank_count = _intentional_blank_count(tuple(items))
    test_padding_blank_count = sum(1 for item in items if item.kind == OutputItemKind.TEST_PADDING_BLANK)
    return ExportSelection(
        kind="quick",
        items=tuple(items),
        source_page_numbers=source_page_numbers,
        selected_spread_source_page_numbers=spread_source_page_numbers,
        description=description,
        intentional_blank_count=intentional_blank_count,
        test_padding_blank_count=test_padding_blank_count,
    )


def suggested_spread_text(source_page_numbers: tuple[int | None, ...]) -> str:
    parts: list[str] = []
    for page_number in source_page_numbers:
        if page_number is None:
            parts.append("BLANK")
        else:
            parts.append(str(page_number))
    return "-".join(parts)


def custom_page_range_selection(start_page: int, end_page: int, composition: DocumentComposition, expand_pairs: bool) -> tuple[ExportSelection, str | None]:
    _validate_range(start_page, end_page, len(composition.source_page_sizes))

    warning: str | None = None
    selected_start = start_page
    selected_end = end_page
    test_padding_blank_count = 0

    start_item = _find_source_item(composition, start_page)
    end_item = _find_source_item(composition, end_page)

    if start_item.side == PageSide.LEFT_EVEN:
        warning = "This range begins on the back side of a duplex sheet. For a representative print test, begin with the preceding source page."
        if expand_pairs and start_page > 1:
            selected_start = start_page - 1

    if expand_pairs and end_item.side == PageSide.RIGHT_ODD:
        if selected_end < len(composition.source_page_sizes):
            selected_end += 1
        else:
            test_padding_blank_count = 1

    start_pos = composition.output_position_for_source_page_number(selected_start)
    end_pos = composition.output_position_for_source_page_number(selected_end)
    if start_pos is None or end_pos is None:
        raise ValueError("The selected page range must be within the source document.")

    selected_items_list = [
        _clone_item(item, output_position=index)
        for index, item in enumerate(_compose_document(composition, start_pos, end_pos), start=1)
    ]
    if test_padding_blank_count:
        reference = selected_items_list[-1]
        selected_items_list.append(_clone_padding_blank(reference, len(selected_items_list) + 1, composition.first_page_side))

    selected_items = tuple(selected_items_list)

    source_page_numbers = _selected_source_numbers(selected_items)
    description = f"Custom page range {suggested_spread_text((selected_start, selected_end))}"
    if any(item.kind == OutputItemKind.INTENTIONAL_BLANK for item in selected_items):
        description += " with intentional blanks"
    return (
        ExportSelection(
            kind="custom",
            items=selected_items,
            source_page_numbers=source_page_numbers,
            selected_spread_source_page_numbers=(selected_start, selected_end),
            description=description,
            intentional_blank_count=_intentional_blank_count(selected_items),
            test_padding_blank_count=test_padding_blank_count,
        ),
        warning,
    )


def suggest_full_export_filename(source_path: Path, shifts: ShiftSettings, scale: float) -> str:
    stem = source_path.stem
    scale_text = format_compact_number(scale)
    if shifts.is_uniform():
        return f"{stem}_GUTTER_{format_mm_compact(shifts.odd_mm)}_{scale_text}pct.pdf"
    return f"{stem}_GUTTER_O{format_mm_compact(shifts.odd_mm)}_E{format_mm_compact(shifts.even_mm)}_{scale_text}pct.pdf"


def _filename_range_text(selection: ExportSelection) -> str:
    spread = selection.selected_spread_source_page_numbers
    has_intentional_blank = any(item.kind == OutputItemKind.INTENTIONAL_BLANK for item in selection.items)
    if selection.kind == "quick":
        if not spread or len(spread) != 2:
            return "selection"
        left, right = spread
        if left is None and right is None:
            return "selection"
        if left is None:
            return f"BLANK-{right}"
        if right is None:
            return f"{left}-BLANK"
        if has_intentional_blank:
            return f"{left}-BLANK-{right}"
        return suggested_spread_text(spread)

    if selection.source_page_numbers:
        if len(selection.source_page_numbers) == 1:
            return str(selection.source_page_numbers[0])
        if has_intentional_blank:
            return f"{selection.source_page_numbers[0]}-BLANK-{selection.source_page_numbers[-1]}"
        return f"{selection.source_page_numbers[0]}-{selection.source_page_numbers[-1]}"
    return "selection"


def suggest_test_export_filename(source_path: Path, selection: ExportSelection, shifts: ShiftSettings, scale: float) -> str:
    stem = source_path.stem
    scale_text = format_compact_number(scale)
    range_text = _filename_range_text(selection)
    if selection.kind == "quick":
        prefix = "TEST_SPREAD"
    else:
        prefix = "TEST_PAGES"
    if shifts.is_uniform():
        return f"{stem}_{prefix}_{range_text}_{format_mm_compact(shifts.odd_mm)}_{scale_text}pct.pdf"
    return f"{stem}_{prefix}_{range_text}_O{format_mm_compact(shifts.odd_mm)}_E{format_mm_compact(shifts.even_mm)}_{scale_text}pct.pdf"
