from pathlib import Path

import fitz

from book_gutter.pdf_document import PdfDocument
from book_gutter.pdf_transform import BindingSide


def make_pdf(path: Path, page_count: int = 4) -> None:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=200 + i * 10, height=300)
        page.insert_text((40, 40), f"Page {i + 1}")
    doc.save(path)
    doc.close()


def test_output_page_dimensions_match_source(tmp_path):
    src = tmp_path / "source.pdf"
    make_pdf(src, 3)
    pdf = PdfDocument(src)
    out = tmp_path / "output.pdf"
    result = pdf.export(out, 100.0, 5.0, BindingSide.LEFT, True)
    assert result.pages_written == 4
    exported = fitz.open(out)
    assert exported.page_count == 4
    assert exported[0].rect.width == pdf.document[0].rect.width
    assert exported[1].rect.height == pdf.document[1].rect.height
    exported.close()
