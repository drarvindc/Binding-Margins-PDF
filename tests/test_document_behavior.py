from pathlib import Path

import fitz

from book_gutter.pdf_document import PdfDocument
from book_gutter.pdf_transform import BindingSide


def make_pdf(path: Path) -> None:
    doc = fitz.open()
    for i, width in enumerate((200, 240, 200)):
        page = doc.new_page(width=width, height=300)
        page.insert_text((40, 40), f"Page {i + 1}", fontsize=16)
    doc.save(path)
    doc.close()


def test_no_page_reordering_and_selectable_text(tmp_path):
    src = tmp_path / "source.pdf"
    make_pdf(src)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    pdf.export(out, 100.0, 5.0, BindingSide.LEFT, False)
    exported = fitz.open(out)
    assert exported.page_count == 3
    assert "Page 1" in exported[0].get_text()
    assert "Page 2" in exported[1].get_text()
    assert "Page 3" in exported[2].get_text()
    exported.close()


def test_mixed_page_sizes_are_preserved(tmp_path):
    src = tmp_path / "mixed.pdf"
    make_pdf(src)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    pdf.export(out, 100.0, 5.0, BindingSide.LEFT, False)
    exported = fitz.open(out)
    assert exported[0].rect.width != exported[1].rect.width
    assert exported[0].rect.width == exported[2].rect.width
    exported.close()


def test_rotated_page_geometry_does_not_crash(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((40, 40), "Rotated page")
    page.set_rotation(90)
    src = tmp_path / "rotated.pdf"
    doc.save(src)
    doc.close()
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    result = pdf.export(out, 100.0, 5.0, BindingSide.LEFT, False)
    assert result.pages_written == 1


def test_uri_links_are_preserved(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 20), "Link")
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 20, 80, 40), "uri": "https://example.com"})
    src = tmp_path / "links.pdf"
    doc.save(src)
    doc.close()
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    pdf.export(out, 100.0, 5.0, BindingSide.LEFT, False)
    exported = fitz.open(out)
    links = exported[0].get_links()
    assert len(links) == 1
    assert links[0]["uri"] == "https://example.com"
    exported.close()
