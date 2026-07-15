from pathlib import Path

import fitz

from book_gutter.pdf_document import PdfDocument
from book_gutter.pdf_transform import BindingSide


def make_pdf(path: Path, page_count: int) -> None:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=200, height=300)
        page.insert_text((40, 40), f"Page {i + 1}")
    doc.save(path)
    doc.close()


def test_odd_page_count_adds_blank_page(tmp_path):
    src = tmp_path / "odd.pdf"
    make_pdf(src, 3)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    result = pdf.export(out, 100.0, 5.0, BindingSide.LEFT, True)
    assert result.blank_page_added is True
    exported = fitz.open(out)
    assert exported.page_count == 4
    assert exported[3].rect.width == exported[2].rect.width
    exported.close()


def test_even_page_count_does_not_add_blank_page(tmp_path):
    src = tmp_path / "even.pdf"
    make_pdf(src, 4)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    result = pdf.export(out, 100.0, 5.0, BindingSide.LEFT, True)
    assert result.blank_page_added is False
    exported = fitz.open(out)
    assert exported.page_count == 4
    exported.close()


def test_disabling_blank_page_preserves_odd_count(tmp_path):
    src = tmp_path / "odd.pdf"
    make_pdf(src, 3)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    result = pdf.export(out, 100.0, 5.0, BindingSide.LEFT, False)
    assert result.blank_page_added is False
    exported = fitz.open(out)
    assert exported.page_count == 3
    exported.close()
