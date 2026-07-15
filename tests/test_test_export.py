from hashlib import sha256
from pathlib import Path

import fitz

from book_gutter.document_layout import DocumentLayout
from book_gutter.export_selection import current_page_pair_selection, custom_page_range_selection
from book_gutter.pdf_document import PdfDocument
from book_gutter.pdf_transform import BindingSide, ShiftSettings


def make_numbered_pdf(path: Path, widths: list[int] | None = None) -> None:
    doc = fitz.open()
    widths = widths or [200] * 6
    for index, width in enumerate(widths, start=1):
        page = doc.new_page(width=width, height=300)
        page.insert_text((40, 40), f"Page {index}")
    doc.save(path)
    doc.close()


def _hash_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _export_quick_test(pdf: PdfDocument, output: Path, current_page: int, page_count: int, scale: float = 100.0, binding_side: BindingSide = BindingSide.LEFT, shifts: ShiftSettings | None = None, layout: DocumentLayout | None = None):
    composition = pdf.compose(layout or DocumentLayout())
    selection = current_page_pair_selection(current_page, composition)
    result = pdf.export_items(
        output,
        selection.items,
        scale,
        shifts or ShiftSettings(5.0, 5.0),
        binding_side,
    )
    return selection, result


def _export_custom_range(pdf: PdfDocument, output: Path, start_page: int, end_page: int, expand_pairs: bool, scale: float = 100.0, binding_side: BindingSide = BindingSide.LEFT, shifts: ShiftSettings | None = None, layout: DocumentLayout | None = None):
    composition = pdf.compose(layout or DocumentLayout())
    selection, warning = custom_page_range_selection(start_page, end_page, composition, expand_pairs)
    result = pdf.export_items(
        output,
        selection.items,
        scale,
        shifts or ShiftSettings(5.0, 5.0),
        binding_side,
    )
    return selection, warning, result


def test_quick_test_export_uses_four_pages_and_preserves_parity(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 6)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    selection, result = _export_quick_test(pdf, out, 3, 6, shifts=ShiftSettings(11.0, 15.0))
    exported = fitz.open(out)
    assert selection.source_page_numbers == (1, 2, 3, 4)
    assert selection.selected_spread_source_page_numbers == (2, 3)
    assert result.source_pages_exported == (1, 2, 3, 4)
    assert result.pages_written == 4
    assert result.blank_pages_added == 0
    assert exported.page_count == 4
    assert [page.get_text().strip().splitlines()[0] for page in exported] == ["Page 1", "Page 2", "Page 3", "Page 4"]
    exported.close()
    pdf.close()


def test_quick_test_export_on_page_15_adds_one_blank(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 15)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    selection, result = _export_quick_test(pdf, out, 15, 15, shifts=ShiftSettings(7.0, 10.0))
    exported = fitz.open(out)
    assert selection.source_page_numbers == (13, 14, 15)
    assert selection.selected_spread_source_page_numbers == (14, 15)
    assert result.source_pages_exported == (13, 14, 15)
    assert result.pages_written == 4
    assert result.blank_pages_added == 1
    assert exported.page_count == 4
    assert "Page 13" in exported[0].get_text()
    assert "Page 14" in exported[1].get_text()
    assert "Page 15" in exported[2].get_text()
    assert exported[3].get_text().strip() == ""
    exported.close()
    pdf.close()


def test_quick_test_export_on_short_documents_pads_to_four_pages(tmp_path):
    cases = [
        (1, (1,), 3),
        (2, (1, 2), 2),
        (3, (1, 2, 3), 1),
    ]
    for page_count, expected_sources, blank_pages in cases:
        src = tmp_path / f"source_{page_count}.pdf"
        make_numbered_pdf(src, [200] * page_count)
        pdf = PdfDocument(src)
        out = tmp_path / f"out_{page_count}.pdf"
        selection, result = _export_quick_test(pdf, out, page_count, page_count)
        exported = fitz.open(out)
        assert selection.source_page_numbers == expected_sources
        assert result.source_pages_exported == expected_sources
        assert result.pages_written == 4
        assert result.blank_pages_added == blank_pages
        assert exported.page_count == 4
        assert exported[-1].get_text().strip() == ""
        exported.close()
        pdf.close()


def test_quick_test_export_preserves_source_text_and_size_for_mixed_pages(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200, 220, 240, 260, 280, 300])
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    selection, result = _export_quick_test(pdf, out, 3, 6, scale=98.0, binding_side=BindingSide.RIGHT, shifts=ShiftSettings(11.0, 15.0))
    exported = fitz.open(out)
    assert selection.source_page_numbers == (1, 2, 3, 4)
    assert result.pages_written == 4
    assert [round(page.rect.width, 1) for page in exported] == [200.0, 220.0, 240.0, 260.0]
    assert [page.get_text().strip().splitlines()[0] for page in exported] == ["Page 1", "Page 2", "Page 3", "Page 4"]
    exported.close()
    pdf.close()


def test_quick_test_export_does_not_modify_source_pdf(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 4)
    before = _hash_file(src)
    pdf = PdfDocument(src)
    out = tmp_path / "out.pdf"
    _export_quick_test(pdf, out, 2, 4, shifts=ShiftSettings(5.0, 5.0))
    after = _hash_file(src)
    pdf.close()
    assert before == after


def test_custom_range_export_includes_intentional_blank_and_preserves_order(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200, 220, 240, 260, 280, 300])
    pdf = PdfDocument(src)
    layout = DocumentLayout().add_blank_before(3)
    out = tmp_path / "out.pdf"
    selection, warning, result = _export_custom_range(pdf, out, 2, 4, False, layout=layout)
    exported = fitz.open(out)
    assert warning is not None
    assert selection.source_page_numbers == (2, 3, 4)
    assert selection.intentional_blank_count == 1
    assert result.source_pages_exported == (2, 3, 4)
    assert result.intentional_blank_pages_added == 1
    assert exported.page_count == 4
    assert exported[0].get_text().strip().startswith("Page 2")
    assert exported[1].get_text().strip() == ""
    assert exported[2].get_text().strip().startswith("Page 3")
    assert exported[3].get_text().strip().startswith("Page 4")
    exported.close()
    pdf.close()


def test_custom_range_export_does_not_modify_source_pdf(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 6)
    before = _hash_file(src)
    pdf = PdfDocument(src)
    layout = DocumentLayout().add_blank_before(3)
    out = tmp_path / "out.pdf"
    _export_custom_range(pdf, out, 2, 4, False, layout=layout)
    after = _hash_file(src)
    pdf.close()
    assert before == after


def test_custom_range_export_preserves_blank_dimensions(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200, 220, 240, 260, 280, 300])
    pdf = PdfDocument(src)
    layout = DocumentLayout().add_blank_before(3)
    out = tmp_path / "out.pdf"
    selection, warning, result = _export_custom_range(pdf, out, 2, 4, False, layout=layout)
    exported = fitz.open(out)
    assert warning is not None
    assert result.source_pages_exported == (2, 3, 4)
    assert [round(page.rect.width, 1) for page in exported] == [220.0, 240.0, 240.0, 260.0]
    exported.close()
    pdf.close()
