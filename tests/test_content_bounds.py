from pathlib import Path

import fitz

from book_gutter.content_bounds import estimate_content_bounds


def make_blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.save(path)
    doc.close()


def make_rect_pdf(path: Path, left: float, top: float, right: float, bottom: float) -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.draw_rect(fitz.Rect(left, top, right, bottom), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)
    doc.close()


def test_blank_page_has_no_content(tmp_path):
    path = tmp_path / "blank.pdf"
    make_blank_pdf(path)
    doc = fitz.open(path)
    estimate = estimate_content_bounds(doc[0])
    assert estimate.has_content is False
    doc.close()


def test_centered_black_rectangle_detected(tmp_path):
    path = tmp_path / "center.pdf"
    make_rect_pdf(path, 70, 100, 130, 160)
    doc = fitz.open(path)
    estimate = estimate_content_bounds(doc[0])
    assert estimate.has_content is True
    assert estimate.margins is not None
    assert estimate.margins.left_mm > 0
    assert estimate.margins.right_mm > 0
    doc.close()


def test_content_near_left_edge_detected(tmp_path):
    path = tmp_path / "left.pdf"
    make_rect_pdf(path, 4, 100, 50, 160)
    doc = fitz.open(path)
    estimate = estimate_content_bounds(doc[0])
    assert estimate.margins is not None
    assert estimate.margins.left_mm < estimate.margins.right_mm
    doc.close()


def test_content_near_right_edge_detected(tmp_path):
    path = tmp_path / "right.pdf"
    make_rect_pdf(path, 150, 100, 196, 160)
    doc = fitz.open(path)
    estimate = estimate_content_bounds(doc[0])
    assert estimate.margins is not None
    assert estimate.margins.right_mm < estimate.margins.left_mm
    doc.close()
