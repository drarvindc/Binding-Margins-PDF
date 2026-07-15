from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .pdf_transform import ShiftSettings
from .units import format_compact_number, format_mm_compact


@dataclass(frozen=True)
class ExportSelection:
    page_indices: tuple[int, ...]
    source_page_numbers: tuple[int, ...]
    append_blank_partner: bool
    description: str


def _validate_range(start_page: int, end_page: int, page_count: int) -> None:
    if page_count <= 0:
        raise ValueError("The source document has no pages.")
    if start_page < 1 or end_page < 1:
        raise ValueError("Page numbers must be 1 or higher.")
    if start_page > page_count or end_page > page_count:
        raise ValueError("The selected page range must be within the source document.")
    if start_page > end_page:
        raise ValueError("The start page must not be after the end page.")


def current_page_pair_selection(current_page: int, page_count: int) -> ExportSelection:
    _validate_range(current_page, current_page, page_count)
    pair_start = current_page if current_page % 2 == 1 else current_page - 1
    pair_end = pair_start + 1
    append_blank_partner = pair_end > page_count
    source_page_numbers = (pair_start,) if append_blank_partner else (pair_start, pair_end)
    page_indices = tuple(number - 1 for number in source_page_numbers)
    if append_blank_partner:
        description = f"Current page pair {pair_start}-{pair_end} plus blank partner"
    else:
        description = f"Current page pair {pair_start}-{pair_end}"
    return ExportSelection(
        page_indices=page_indices,
        source_page_numbers=source_page_numbers,
        append_blank_partner=append_blank_partner,
        description=description,
    )


def custom_page_range_selection(start_page: int, end_page: int, page_count: int, expand_pairs: bool) -> tuple[ExportSelection, str | None]:
    _validate_range(start_page, end_page, page_count)

    warning: str | None = None
    selected_start = start_page
    selected_end = end_page
    append_blank_partner = False

    if start_page % 2 == 0:
        warning = "This range begins on the back side of a duplex sheet. For a representative print test, begin with the preceding odd page."
        if expand_pairs and start_page > 1:
            selected_start = start_page - 1

    if expand_pairs and selected_end % 2 == 1:
        if selected_end < page_count:
            selected_end += 1
        else:
            append_blank_partner = True

    source_page_numbers = tuple(range(selected_start, selected_end + 1))
    page_indices = tuple(number - 1 for number in source_page_numbers)
    description = f"Custom page range {selected_start}-{selected_end}"
    if append_blank_partner:
        description += " plus blank partner"
    return (
        ExportSelection(
            page_indices=page_indices,
            source_page_numbers=source_page_numbers,
            append_blank_partner=append_blank_partner,
            description=description,
        ),
        warning,
    )


def suggest_full_export_filename(source_path: Path, shifts: ShiftSettings, scale: float) -> str:
    stem = source_path.stem
    scale_text = format_compact_number(scale)
    if shifts.is_uniform():
        return f"{stem}_GUTTER_{format_mm_compact(shifts.odd_mm)}_{scale_text}pct.pdf"
    return f"{stem}_GUTTER_O{format_mm_compact(shifts.odd_mm)}_E{format_mm_compact(shifts.even_mm)}_{scale_text}pct.pdf"


def suggest_test_export_filename(source_path: Path, selection: ExportSelection, shifts: ShiftSettings, scale: float) -> str:
    stem = source_path.stem
    scale_text = format_compact_number(scale)
    if selection.source_page_numbers:
        if len(selection.source_page_numbers) == 1 and selection.append_blank_partner:
            range_text = f"{selection.source_page_numbers[0]}-{selection.source_page_numbers[0] + 1}"
        elif selection.append_blank_partner:
            range_text = f"{selection.source_page_numbers[0]}-{selection.source_page_numbers[-1] + 1}"
        else:
            range_text = f"{selection.source_page_numbers[0]}-{selection.source_page_numbers[-1]}"
    else:
        range_text = "selection"
    if shifts.is_uniform():
        return f"{stem}_TEST_PAGES_{range_text}_{format_mm_compact(shifts.odd_mm)}_{scale_text}pct.pdf"
    return f"{stem}_TEST_PAGES_{range_text}_O{format_mm_compact(shifts.odd_mm)}_E{format_mm_compact(shifts.even_mm)}_{scale_text}pct.pdf"
