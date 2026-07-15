from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import fitz
import numpy as np

from .units import points_to_mm, mm_to_points
from .pdf_transform import BindingSide, page_shift_sign


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


def transformed_margins(
    page: fitz.Page,
    estimate: ContentBoundsEstimate,
    scale: float,
    shift_mm: float,
    binding_side: BindingSide,
    page_index: int,
) -> Optional[ContentMargins]:
    if not estimate.has_content or estimate.bbox is None:
        return None

    sign = page_shift_sign(page_index, binding_side)
    shift_points = mm_to_points(shift_mm) * sign
    page_width = page.rect.width
    page_height = page.rect.height
    center_x = page_width / 2.0 + shift_points
    center_y = page_height / 2.0
    factor = scale / 100.0
    content_left = center_x + (estimate.bbox.x0 - page_width / 2.0) * factor
    content_right = center_x + (estimate.bbox.x1 - page_width / 2.0) * factor
    content_top = center_y + (estimate.bbox.y0 - page_height / 2.0) * factor
    content_bottom = center_y + (estimate.bbox.y1 - page_height / 2.0) * factor

    return ContentMargins(
        left_mm=points_to_mm(content_left - 0.0),
        right_mm=points_to_mm(page_width - content_right),
        top_mm=points_to_mm(content_top - 0.0),
        bottom_mm=points_to_mm(page_height - content_bottom),
    )


def transformed_content_crosses_edge(page: fitz.Page, estimate: ContentBoundsEstimate, scale: float, shift_mm: float, binding_side: BindingSide, page_index: int) -> bool:
    if not estimate.has_content or estimate.bbox is None:
        return False
    sign = page_shift_sign(page_index, binding_side)
    shift_points = mm_to_points(shift_mm) * sign
    factor = scale / 100.0
    center_x = page.rect.width / 2.0 + shift_points
    center_y = page.rect.height / 2.0
    content_left = center_x + (estimate.bbox.x0 - page.rect.width / 2.0) * factor
    content_right = center_x + (estimate.bbox.x1 - page.rect.width / 2.0) * factor
    content_top = center_y + (estimate.bbox.y0 - page.rect.height / 2.0) * factor
    content_bottom = center_y + (estimate.bbox.y1 - page.rect.height / 2.0) * factor
    return content_left < 0 or content_top < 0 or content_right > page.rect.width or content_bottom > page.rect.height
