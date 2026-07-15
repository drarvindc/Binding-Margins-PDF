import fitz

from book_gutter.pdf_document import PdfDocument, PdfDocumentError
from book_gutter.pdf_transform import BindingSide, target_rect_for_page


def test_100_percent_scale_preserves_source_width_and_height():
    rect = fitz.Rect(0, 0, 210, 297)
    target = target_rect_for_page(rect, 100.0, 5.0, 0, BindingSide.LEFT)
    assert target.width == rect.width
    assert target.height == rect.height


def test_reduced_scale_stays_centered_before_shift():
    rect = fitz.Rect(0, 0, 210, 297)
    target = target_rect_for_page(rect, 90.0, 0.0, 0, BindingSide.LEFT)
    assert abs(target.x0 + target.x1 - rect.x0 - rect.x1) < 1e-6
    assert abs(target.y0 + target.y1 - rect.y0 - rect.y1) < 1e-6


def test_output_file_cannot_equal_source_file(tmp_path):
    src = tmp_path / "source.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=300)
    doc.save(src)
    doc.close()
    pdf = PdfDocument(src)
    try:
        try:
            pdf.export(src, 100.0, 5.0, BindingSide.LEFT, False)
            raise AssertionError("Expected PdfDocumentError")
        except PdfDocumentError as exc:
            assert "different from the source file" in str(exc)
    finally:
        pdf.close()
