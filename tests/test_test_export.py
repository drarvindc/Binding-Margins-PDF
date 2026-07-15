from hashlib import sha256
from pathlib import Path

import fitz

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


def test_source_page_parity_is_preserved_after_subset_export(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 12)
    pdf = PdfDocument(src)
    selection, warning = custom_page_range_selection(10, 12, 12, False)
    assert warning is not None
    out = tmp_path / "out.pdf"
    result = pdf.export_pages(out, selection.page_indices, 100.0, ShiftSettings(11.0, 15.0), BindingSide.LEFT, append_blank_partner=selection.append_blank_partner)
    exported = fitz.open(out)
    assert result.source_pages_exported == (10, 11, 12)
    assert exported.page_count == 3
    assert "Page 10" in exported[0].get_text()
    assert "Page 11" in exported[1].get_text()
    assert "Page 12" in exported[2].get_text()
    exported.close()
    pdf.close()


def test_final_unmatched_odd_page_receives_blank_partner(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 3)
    pdf = PdfDocument(src)
    selection = current_page_pair_selection(3, 3)
    out = tmp_path / "out.pdf"
    result = pdf.export_pages(out, selection.page_indices, 100.0, ShiftSettings(5.0, 5.0), BindingSide.LEFT, append_blank_partner=selection.append_blank_partner)
    exported = fitz.open(out)
    assert result.blank_partner_added is True
    assert exported.page_count == 2
    assert "Page 3" in exported[0].get_text()
    assert exported[1].get_text().strip() == ""
    exported.close()
    pdf.close()


def test_test_export_does_not_modify_source_pdf(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 4)
    before = _hash_file(src)
    pdf = PdfDocument(src)
    selection = current_page_pair_selection(2, 4)
    out = tmp_path / "out.pdf"
    pdf.export_pages(out, selection.page_indices, 100.0, ShiftSettings(5.0, 5.0), BindingSide.LEFT, append_blank_partner=selection.append_blank_partner)
    after = _hash_file(src)
    pdf.close()
    assert before == after


def test_test_export_page_order_remains_correct(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200] * 6)
    pdf = PdfDocument(src)
    selection, _ = custom_page_range_selection(2, 5, 6, True)
    out = tmp_path / "out.pdf"
    pdf.export_pages(out, selection.page_indices, 100.0, ShiftSettings(11.0, 15.0), BindingSide.LEFT, append_blank_partner=selection.append_blank_partner)
    exported = fitz.open(out)
    assert [page.get_text().strip().splitlines()[0] for page in exported] == ["Page 1", "Page 2", "Page 3", "Page 4", "Page 5", "Page 6"]
    exported.close()
    pdf.close()


def test_mixed_page_sizes_remain_correct_in_a_test_range(tmp_path):
    src = tmp_path / "source.pdf"
    make_numbered_pdf(src, [200, 220, 240, 260, 280, 300])
    pdf = PdfDocument(src)
    selection, _ = custom_page_range_selection(2, 5, 6, True)
    out = tmp_path / "out.pdf"
    pdf.export_pages(out, selection.page_indices, 98.0, ShiftSettings(11.0, 15.0), BindingSide.RIGHT, append_blank_partner=selection.append_blank_partner)
    exported = fitz.open(out)
    assert [round(page.rect.width, 1) for page in exported] == [200.0, 220.0, 240.0, 260.0, 280.0, 300.0]
    exported.close()
    pdf.close()
