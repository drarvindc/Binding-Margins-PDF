from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FacingSpread:
    left_page_number: int | None
    right_page_number: int | None
    spread_start_page_number: int
    spread_end_page_number: int

    @property
    def has_left_page(self) -> bool:
        return self.left_page_number is not None

    @property
    def has_right_page(self) -> bool:
        return self.right_page_number is not None


def clamp_page_number(page_number: int, page_count: int) -> int:
    if page_count <= 0:
        raise ValueError("The source document has no pages.")
    return max(1, min(page_number, page_count))


def facing_spread_start_page(page_number: int, page_count: int) -> int:
    page_number = clamp_page_number(page_number, page_count)
    if page_number == 1:
        return 1
    return page_number if page_number % 2 == 0 else page_number - 1


def facing_spread_end_page(page_number: int, page_count: int) -> int:
    page_number = clamp_page_number(page_number, page_count)
    if page_number == 1:
        return 1
    if page_number % 2 == 0:
        return page_number + 1 if page_number < page_count else page_number
    return page_number


def resolve_facing_spread(page_number: int, page_count: int) -> FacingSpread:
    page_number = clamp_page_number(page_number, page_count)
    if page_number == 1:
        return FacingSpread(
            left_page_number=None,
            right_page_number=1,
            spread_start_page_number=1,
            spread_end_page_number=1,
        )

    if page_number % 2 == 0:
        left = page_number
        right = page_number + 1 if page_number < page_count else None
        spread_end = right or page_number
        return FacingSpread(
            left_page_number=left,
            right_page_number=right,
            spread_start_page_number=left,
            spread_end_page_number=spread_end,
        )

    left = page_number - 1
    return FacingSpread(
        left_page_number=left,
        right_page_number=page_number,
        spread_start_page_number=left,
        spread_end_page_number=page_number,
    )


def facing_final_spread_start(page_count: int) -> int:
    if page_count <= 1:
        return 1
    return page_count if page_count % 2 == 0 else page_count - 1


def next_facing_page_number(page_number: int, page_count: int) -> int:
    page_number = clamp_page_number(page_number, page_count)
    if page_count <= 1:
        return 1
    if page_number == 1:
        return 2
    current_start = facing_spread_start_page(page_number, page_count)
    next_start = current_start + 2
    return min(next_start, facing_final_spread_start(page_count))


def previous_facing_page_number(page_number: int, page_count: int) -> int:
    page_number = clamp_page_number(page_number, page_count)
    if page_number <= 1:
        return 1
    current_start = facing_spread_start_page(page_number, page_count)
    return 1 if current_start <= 2 else current_start - 2


def format_facing_indicator(spread: FacingSpread, page_count: int) -> str:
    if spread.left_page_number is None and spread.right_page_number == 1:
        return f"Page 1 of {page_count}"
    if spread.right_page_number is None:
        return f"Page {spread.left_page_number} of {page_count} with right placeholder"
    if spread.left_page_number == 1 and spread.right_page_number == 1:
        return f"Page 1 of {page_count}"
    if spread.left_page_number is None:
        return f"Page {spread.right_page_number} of {page_count}"
    return f"Pages {spread.left_page_number}-{spread.right_page_number} of {page_count}"
