from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import fitz
import numpy as np

from .pdf_transform import BindingSide, ShiftSpec, normalize_shift_settings, page_shift_mm, page_shift_sign
from .units import mm_to_points, points_to_mm


@dataclass(frozen=True)
class ContentMargins:
    left_mm: float
    right_mm: float
    top_mm: float
    bottom_mm: float


@dataclass(frozen=True)
class ContentBoundsEstimate:
    bbox: Optional[fitz.Rect]
    margins: Optional[ContentMargins]
    has_content: bool


def _pixmap_to_rgb_array(pix: fitz.Pixmap) -> np.ndarray:
    array = np.frombuffer(pix.samples, dtype=np.uint8)
    return array.reshape(pix.height, pix.width, pix.n)


def estimate_content_bounds(page: fitz.Page, threshold: int = 245, dpi: int = 48) -> ContentBoundsEstimate:
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    data = _pixmap_to_rgb_array(pix)
    if data.shape[2] > 3:
        data = data[:, :, :3]
    mask = np.any(data < threshold, axis=2)
    if not np.any(mask):
        return ContentBoundsEstimate(bbox=None, margins=None, has_content=False)

    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    top = int(rows[0])
    bottom = int(rows[-1])
    left = int(cols[0])
    right = int(cols[-1])
    scale = page.rect.width / pix.width
    bbox = fitz.Rect(left * scale, top * scale, (right + 1) * scale, (bottom + 1) * scale)
    margins = ContentMargins(
        left_mm=points_to_mm(bbox.x0 - page.rect.x0),
        right_mm=points_to_mm(page.rect.x1 - bbox.x1),
        top_mm=points_to_mm(bbox.y0 - page.rect.y0),
        bottom_mm=points_to_mm(page.rect.y1 - bbox.y1),
    )
    return ContentBoundsEstimate(bbox=bbox, margins=margins, has_content=True)


def _transformed_content_rect(
    page: fitz.Page,
    estimate: ContentBoundsEstimate,
    scale: float,
    shift_spec: ShiftSpec,
    binding_side: BindingSide,
    page_index: int,
) -> Optional[fitz.Rect]:
    if not estimate.has_content or estimate.bbox is None:
        return None

    normalized = normalize_shift_settings(shift_spec)
    shift_points = mm_to_points(page_shift_mm(normalized, page_index)) * page_shift_sign(page_index, binding_side)
    factor = scale / 100.0
    center_x = page.rect.width / 2.0 + shift_points
    center_y = page.rect.height / 2.0
    return fitz.Rect(
        center_x + (estimate.bbox.x0 - page.rect.width / 2.0) * factor,
        center_y + (estimate.bbox.y0 - page.rect.height / 2.0) * factor,
        center_x + (estimate.bbox.x1 - page.rect.width / 2.0) * factor,
        center_y + (estimate.bbox.y1 - page.rect.height / 2.0) * factor,
    )


def transformed_margins(
    page: fitz.Page,
    estimate: ContentBoundsEstimate,
    scale: float,
    shift_spec: ShiftSpec,
    binding_side: BindingSide,
    page_index: int,
) -> Optional[ContentMargins]:
    rect = _transformed_content_rect(page, estimate, scale, shift_spec, binding_side, page_index)
    if rect is None:
        return None
    return ContentMargins(
        left_mm=points_to_mm(rect.x0 - page.rect.x0),
        right_mm=points_to_mm(page.rect.x1 - rect.x1),
        top_mm=points_to_mm(rect.y0 - page.rect.y0),
        bottom_mm=points_to_mm(page.rect.y1 - rect.y1),
    )


def transformed_content_crosses_edge(
    page: fitz.Page,
    estimate: ContentBoundsEstimate,
    scale: float,
    shift_spec: ShiftSpec,
    binding_side: BindingSide,
    page_index: int,
) -> bool:
    rect = _transformed_content_rect(page, estimate, scale, shift_spec, binding_side, page_index)
    if rect is None:
        return False
    return rect.x0 < page.rect.x0 or rect.y0 < page.rect.y0 or rect.x1 > page.rect.x1 or rect.y1 > page.rect.y1
