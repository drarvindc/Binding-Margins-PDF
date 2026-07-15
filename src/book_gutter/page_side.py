from __future__ import annotations

from enum import Enum


class PageSide(str, Enum):
    RIGHT_ODD = "right_odd"
    LEFT_EVEN = "left_even"

    @property
    def label(self) -> str:
        if self == PageSide.RIGHT_ODD:
            return "Right / Odd"
        return "Left / Even"

    @property
    def short_label(self) -> str:
        if self == PageSide.RIGHT_ODD:
            return "right/odd"
        return "left/even"

    @property
    def parity_label(self) -> str:
        return "odd" if self == PageSide.RIGHT_ODD else "even"

    def opposite(self) -> "PageSide":
        return PageSide.LEFT_EVEN if self == PageSide.RIGHT_ODD else PageSide.RIGHT_ODD

    @classmethod
    def from_first_page_setting(cls, source_page_one_on_right: bool) -> "PageSide":
        return cls.RIGHT_ODD if source_page_one_on_right else cls.LEFT_EVEN
