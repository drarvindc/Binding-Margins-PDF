from __future__ import annotations

from .document_layout import DocumentComposition, FacingSpread


def resolve_facing_spread(composition: DocumentComposition, active_output_position: int) -> FacingSpread:
    return composition.spread_for_output_position(active_output_position)


def format_facing_indicator(spread: FacingSpread) -> str:
    if spread.left_item is None and spread.right_item is None:
        return "No output item selected"
    if spread.left_item is None:
        right = spread.right_item
        assert right is not None
        return f"Output {right.output_position} with left placeholder"
    if spread.right_item is None:
        left = spread.left_item
        return f"Output {left.output_position} with right placeholder"
    return f"Output {spread.spread_start_position}-{spread.spread_end_position}"


def next_output_position(active_output_position: int, item_count: int) -> int:
    if item_count <= 0:
        raise ValueError("The source document has no pages.")
    return min(active_output_position + 1, item_count)


def previous_output_position(active_output_position: int, item_count: int) -> int:
    if item_count <= 0:
        raise ValueError("The source document has no pages.")
    return max(active_output_position - 1, 1)
