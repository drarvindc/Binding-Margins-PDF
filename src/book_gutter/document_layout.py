from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .page_side import PageSide


class BlankPlacement(str, Enum):
    BEFORE = "before"
    AFTER = "after"


class OutputItemKind(str, Enum):
    SOURCE_PAGE = "source_page"
    INTENTIONAL_BLANK = "intentional_blank"
    AUTOMATIC_FINAL_BLANK = "automatic_final_blank"
    TEST_PADDING_BLANK = "test_padding_blank"


@dataclass(frozen=True)
class IntentionalBlankInsertion:
    insertion_id: int
    source_page_number: int
    placement: BlankPlacement


@dataclass(frozen=True)
class OutputItem:
    kind: OutputItemKind
    output_position: int
    side: PageSide
    page_width_pt: float
    page_height_pt: float
    source_page_index: int | None = None
    source_page_number: int | None = None
    blank_insertion_id: int | None = None
    blank_reference_source_page_number: int | None = None
    blank_placement: BlankPlacement | None = None

    @property
    def is_source_page(self) -> bool:
        return self.kind == OutputItemKind.SOURCE_PAGE

    @property
    def is_blank(self) -> bool:
        return self.kind != OutputItemKind.SOURCE_PAGE


@dataclass(frozen=True)
class FacingSpread:
    left_item: OutputItem | None
    right_item: OutputItem | None
    spread_start_position: int
    spread_end_position: int

    @property
    def has_left_item(self) -> bool:
        return self.left_item is not None

    @property
    def has_right_item(self) -> bool:
        return self.right_item is not None


@dataclass(frozen=True)
class DocumentComposition:
    first_page_side: PageSide
    source_page_sizes: tuple[tuple[float, float], ...]
    items: tuple[OutputItem, ...]
    source_page_number_to_output_position: dict[int, int]
    blank_id_to_output_position: dict[int, int]

    def item_at_output_position(self, output_position: int) -> OutputItem:
        if output_position < 1 or output_position > len(self.items):
            raise IndexError("Output position is outside the composed sequence.")
        return self.items[output_position - 1]

    def source_item(self, source_page_number: int) -> OutputItem | None:
        output_position = self.source_page_number_to_output_position.get(source_page_number)
        if output_position is None:
            return None
        return self.item_at_output_position(output_position)

    def blank_item(self, insertion_id: int) -> OutputItem | None:
        output_position = self.blank_id_to_output_position.get(insertion_id)
        if output_position is None:
            return None
        return self.item_at_output_position(output_position)

    def source_page_numbers(self) -> tuple[int, ...]:
        return tuple(item.source_page_number for item in self.items if item.is_source_page and item.source_page_number is not None)

    def locate_source_page_position(self, source_page_number: int) -> int | None:
        return self.source_page_number_to_output_position.get(source_page_number)

    def output_position_for_source_page_number(self, source_page_number: int) -> int | None:
        return self.source_page_number_to_output_position.get(source_page_number)

    def side_for_output_position(self, output_position: int) -> PageSide:
        item = self.item_at_output_position(output_position)
        return item.side

    def _neighbor(self, output_position: int, offset: int) -> OutputItem | None:
        candidate = output_position + offset
        if candidate < 1 or candidate > len(self.items):
            return None
        return self.items[candidate - 1]

    def spread_for_output_position(self, output_position: int) -> FacingSpread:
        current = self.item_at_output_position(output_position)
        if current.side == PageSide.LEFT_EVEN:
            partner = self._neighbor(output_position, 1)
            if partner is not None and partner.side == PageSide.RIGHT_ODD:
                return FacingSpread(current, partner, output_position, output_position + 1)
            return FacingSpread(current, None, output_position, output_position)

        partner = self._neighbor(output_position, -1)
        if partner is not None and partner.side == PageSide.LEFT_EVEN:
            return FacingSpread(partner, current, output_position - 1, output_position)
        return FacingSpread(None, current, output_position, output_position)

    def selected_pair_for_quick_test(self, output_position: int) -> tuple[OutputItem, OutputItem]:
        current = self.item_at_output_position(output_position)
        if current.side == PageSide.LEFT_EVEN:
            partner = self._neighbor(output_position, 1)
            if partner is not None and partner.side == PageSide.RIGHT_ODD:
                return current, partner
            partner = self._neighbor(output_position, -1)
            if partner is not None and partner.side == PageSide.RIGHT_ODD:
                return partner, current
            return current, current

        partner = self._neighbor(output_position, -1)
        if partner is not None and partner.side == PageSide.LEFT_EVEN:
            return partner, current
        partner = self._neighbor(output_position, 1)
        if partner is not None and partner.side == PageSide.LEFT_EVEN:
            return current, partner
        return current, current

    def inserted_blank_summaries(self) -> tuple[str, ...]:
        summaries: list[str] = []
        for item in self.items:
            if item.kind != OutputItemKind.INTENTIONAL_BLANK:
                continue
            if item.blank_placement == BlankPlacement.BEFORE:
                summaries.append(f"Blank before source page {item.blank_reference_source_page_number}")
            else:
                summaries.append(f"Blank after source page {item.blank_reference_source_page_number}")
        return tuple(summaries)


@dataclass(frozen=True)
class DocumentLayout:
    first_page_side: PageSide = PageSide.RIGHT_ODD
    intentional_blanks: tuple[IntentionalBlankInsertion, ...] = ()

    def reset_for_new_document(self) -> "DocumentLayout":
        return DocumentLayout(first_page_side=PageSide.RIGHT_ODD, intentional_blanks=())

    def with_first_page_side(self, first_page_side: PageSide) -> "DocumentLayout":
        return DocumentLayout(first_page_side=first_page_side, intentional_blanks=self.intentional_blanks)

    def _next_blank_id(self) -> int:
        if not self.intentional_blanks:
            return 1
        return max(blank.insertion_id for blank in self.intentional_blanks) + 1

    def add_blank_before(self, source_page_number: int) -> "DocumentLayout":
        insertion = IntentionalBlankInsertion(self._next_blank_id(), source_page_number, BlankPlacement.BEFORE)
        return DocumentLayout(first_page_side=self.first_page_side, intentional_blanks=self.intentional_blanks + (insertion,))

    def add_blank_after(self, source_page_number: int) -> "DocumentLayout":
        insertion = IntentionalBlankInsertion(self._next_blank_id(), source_page_number, BlankPlacement.AFTER)
        return DocumentLayout(first_page_side=self.first_page_side, intentional_blanks=self.intentional_blanks + (insertion,))

    def remove_blank(self, insertion_id: int) -> "DocumentLayout":
        return DocumentLayout(
            first_page_side=self.first_page_side,
            intentional_blanks=tuple(blank for blank in self.intentional_blanks if blank.insertion_id != insertion_id),
        )

    def clear_blanks(self) -> "DocumentLayout":
        return DocumentLayout(first_page_side=self.first_page_side, intentional_blanks=())

    @staticmethod
    def side_for_output_position(output_position: int, first_page_side: PageSide) -> PageSide:
        if output_position < 1:
            raise ValueError("Output positions start at 1.")
        if first_page_side == PageSide.RIGHT_ODD:
            return PageSide.RIGHT_ODD if output_position % 2 == 1 else PageSide.LEFT_EVEN
        return PageSide.LEFT_EVEN if output_position % 2 == 1 else PageSide.RIGHT_ODD

    def compose(self, source_page_sizes: Sequence[tuple[float, float]]) -> DocumentComposition:
        before_map: dict[int, list[IntentionalBlankInsertion]] = defaultdict(list)
        after_map: dict[int, list[IntentionalBlankInsertion]] = defaultdict(list)
        for insertion in self.intentional_blanks:
            if insertion.placement == BlankPlacement.BEFORE:
                before_map[insertion.source_page_number].append(insertion)
            else:
                after_map[insertion.source_page_number].append(insertion)

        items: list[OutputItem] = []
        source_page_number_to_output_position: dict[int, int] = {}
        blank_id_to_output_position: dict[int, int] = {}

        def append_item(item: OutputItem) -> None:
            item_position = len(items) + 1
            items.append(
                OutputItem(
                    kind=item.kind,
                    output_position=item_position,
                    side=item.side,
                    page_width_pt=item.page_width_pt,
                    page_height_pt=item.page_height_pt,
                    source_page_index=item.source_page_index,
                    source_page_number=item.source_page_number,
                    blank_insertion_id=item.blank_insertion_id,
                    blank_reference_source_page_number=item.blank_reference_source_page_number,
                    blank_placement=item.blank_placement,
                )
            )

        for source_page_number, page_size in enumerate(source_page_sizes, start=1):
            for insertion in before_map.get(source_page_number, ()):
                side = self.side_for_output_position(len(items) + 1, self.first_page_side)
                blank = OutputItem(
                    kind=OutputItemKind.INTENTIONAL_BLANK,
                    output_position=len(items) + 1,
                    side=side,
                    page_width_pt=page_size[0],
                    page_height_pt=page_size[1],
                    blank_insertion_id=insertion.insertion_id,
                    blank_reference_source_page_number=source_page_number,
                    blank_placement=BlankPlacement.BEFORE,
                )
                append_item(blank)
                blank_id_to_output_position[insertion.insertion_id] = blank.output_position

            side = self.side_for_output_position(len(items) + 1, self.first_page_side)
            source_item = OutputItem(
                kind=OutputItemKind.SOURCE_PAGE,
                output_position=len(items) + 1,
                side=side,
                page_width_pt=page_size[0],
                page_height_pt=page_size[1],
                source_page_index=source_page_number - 1,
                source_page_number=source_page_number,
            )
            append_item(source_item)
            source_page_number_to_output_position[source_page_number] = source_item.output_position

            for insertion in after_map.get(source_page_number, ()):
                side = self.side_for_output_position(len(items) + 1, self.first_page_side)
                blank = OutputItem(
                    kind=OutputItemKind.INTENTIONAL_BLANK,
                    output_position=len(items) + 1,
                    side=side,
                    page_width_pt=page_size[0],
                    page_height_pt=page_size[1],
                    blank_insertion_id=insertion.insertion_id,
                    blank_reference_source_page_number=source_page_number,
                    blank_placement=BlankPlacement.AFTER,
                )
                append_item(blank)
                blank_id_to_output_position[insertion.insertion_id] = blank.output_position

        return DocumentComposition(
            first_page_side=self.first_page_side,
            source_page_sizes=tuple(source_page_sizes),
            items=tuple(items),
            source_page_number_to_output_position=source_page_number_to_output_position,
            blank_id_to_output_position=blank_id_to_output_position,
        )
