from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union

import fitz

from .units import mm_to_points


class BindingSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class ShiftSettings:
    odd_mm: float
    even_mm: float

    def is_uniform(self) -> bool:
        return abs(self.odd_mm - self.even_mm) < 1e-9

    def mm_for_page(self, page_index: int) -> float:
        return self.odd_mm if is_odd_page(page_index) else self.even_mm


ShiftSpec = Union[float, ShiftSettings]


@dataclass(frozen=True)
class PagePlacement:
    page_number: int
    is_odd: bool
    shift_sign: int
    shift_mm: float
    shift_points: float
    scale: float
    source_rect: fitz.Rect
    target_rect: fitz.Rect
    outer_warning: bool
    visible_clip_warning: bool


def is_odd_page(page_index: int) -> bool:
    return (page_index + 1) % 2 == 1


def normalize_shift_settings(shift_spec: ShiftSpec) -> ShiftSettings:
    if isinstance(shift_spec, ShiftSettings):
        return shift_spec
    return ShiftSettings(odd_mm=float(shift_spec), even_mm=float(shift_spec))


def page_shift_mm(shift_spec: ShiftSpec, page_index: int) -> float:
    return normalize_shift_settings(shift_spec).mm_for_page(page_index)


def page_shift_sign(page_index: int, binding_side: BindingSide) -> int:
    odd = is_odd_page(page_index)
    if binding_side == BindingSide.LEFT:
        return 1 if odd else -1
    return -1 if odd else 1


def page_shift_points(shift_spec: ShiftSpec, page_index: int, binding_side: BindingSide) -> float:
    return mm_to_points(page_shift_mm(shift_spec, page_index)) * page_shift_sign(page_index, binding_side)


def target_rect_for_page(page_rect: fitz.Rect, scale: float, shift_spec: ShiftSpec, page_index: int, binding_side: BindingSide) -> fitz.Rect:
    scaled_width = page_rect.width * scale / 100.0
    scaled_height = page_rect.height * scale / 100.0
    center_x = page_rect.x0 + page_rect.width / 2.0 + page_shift_points(shift_spec, page_index, binding_side)
    center_y = page_rect.y0 + page_rect.height / 2.0
    return fitz.Rect(
        center_x - scaled_width / 2.0,
        center_y - scaled_height / 2.0,
        center_x + scaled_width / 2.0,
        center_y + scaled_height / 2.0,
    )


def placement_for_page(page_rect: fitz.Rect, scale: float, shift_spec: ShiftSpec, page_index: int, binding_side: BindingSide) -> PagePlacement:
    normalized = normalize_shift_settings(shift_spec)
    target = target_rect_for_page(page_rect, scale, normalized, page_index, binding_side)
    active_shift_mm = normalized.mm_for_page(page_index)
    return PagePlacement(
        page_number=page_index + 1,
        is_odd=is_odd_page(page_index),
        shift_sign=page_shift_sign(page_index, binding_side),
        shift_mm=active_shift_mm,
        shift_points=page_shift_points(normalized, page_index, binding_side),
        scale=scale,
        source_rect=fitz.Rect(page_rect),
        target_rect=target,
        outer_warning=target.x0 < page_rect.x0 or target.x1 > page_rect.x1,
        visible_clip_warning=False,
    )
