from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz

from .content_bounds import ContentBoundsEstimate, estimate_content_bounds
from .pdf_transform import BindingSide, placement_for_page


@dataclass(frozen=True)
class PageInfo:
    index: int
    width_pt: float
    height_pt: float


@dataclass(frozen=True)
class DocumentInfo:
    source_path: Path
    file_name: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    mixed_page_sizes: bool


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    pages_written: int
    blank_page_added: bool


class PdfDocumentError(RuntimeError):
    pass


class PdfDocument:
    def __init__(self, path: Path):
        self.path = path
        self._doc = self._open(path)

    @staticmethod
    def _open(path: Path) -> fitz.Document:
        if not path.exists():
            raise PdfDocumentError("The selected PDF file does not exist.")
        try:
            doc = fitz.open(path)
        except Exception as exc:  # pragma: no cover - fitz errors are translated
            raise PdfDocumentError("The PDF could not be opened.") from exc
        if doc.needs_pass:
            doc.close()
            raise PdfDocumentError("The PDF is encrypted or password-protected.")
        if doc.page_count <= 0:
            doc.close()
            raise PdfDocumentError("The PDF has no pages.")
        return doc

    @property
    def document(self) -> fitz.Document:
        return self._doc

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()

    def info(self) -> DocumentInfo:
        sizes = [(page.rect.width, page.rect.height) for page in self._doc]
        mixed = len({(round(w, 3), round(h, 3)) for w, h in sizes}) > 1
        return DocumentInfo(
            source_path=self.path,
            file_name=self.path.name,
            page_count=self._doc.page_count,
            page_sizes=sizes,
            mixed_page_sizes=mixed,
        )

    def page_info(self, page_index: int) -> PageInfo:
        page = self._doc[page_index]
        return PageInfo(index=page_index, width_pt=page.rect.width, height_pt=page.rect.height)

    def preview_pixmap(self, page_index: int, scale: float, shift_mm: float, binding_side: BindingSide, show_original: bool, dpi: int = 110) -> fitz.Pixmap:
        page = self._doc[page_index]
        return page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)

    def content_estimate(self, page_index: int) -> ContentBoundsEstimate:
        return estimate_content_bounds(self._doc[page_index])

    def export(
        self,
        output_path: Path,
        scale: float,
        shift_mm: float,
        binding_side: BindingSide,
        add_blank_final_page: bool,
        progress_callback: Optional[callable] = None,
        cancel_check: Optional[callable] = None,
    ) -> ExportResult:
        if self.path.resolve(strict=False) == output_path.resolve(strict=False):
            raise PdfDocumentError("The output file must be different from the source file.")

        out_doc = fitz.open()
        blank_added = False
        temp_output = output_path.with_suffix(output_path.suffix + ".tmp")
        pages_written = 0
        try:
            for index in range(self._doc.page_count):
                if cancel_check and cancel_check():
                    raise PdfDocumentError("Export cancelled.")
                src_page = self._doc[index]
                out_page = out_doc.new_page(width=src_page.rect.width, height=src_page.rect.height)
                placement = placement_for_page(src_page.rect, scale, shift_mm, index, binding_side)
                target = placement.target_rect
                out_page.show_pdf_page(target, self._doc, index, keep_proportion=True, clip=None, rotate=0)
                self._copy_links(src_page, out_page, placement)
                pages_written += 1
                if progress_callback:
                    progress_callback(index + 1, self._doc.page_count + (1 if add_blank_final_page and self._doc.page_count % 2 == 1 else 0))

            if add_blank_final_page and self._doc.page_count % 2 == 1:
                last = self._doc[-1].rect
                out_doc.new_page(width=last.width, height=last.height)
                blank_added = True
                pages_written += 1

            out_doc.save(temp_output, garbage=4, deflate=True, clean=True)
            temp_output.replace(output_path)
            return ExportResult(output_path=output_path, pages_written=pages_written, blank_page_added=blank_added)
        except Exception:
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
            raise
        finally:
            out_doc.close()

    @staticmethod
    def _copy_links(src_page: fitz.Page, out_page: fitz.Page, placement) -> None:
        for link in src_page.get_links():
            link_dict = {key: value for key, value in link.items() if key not in {"xref", "id"}}
            rect = link_dict.get("from")
            if rect is None:
                continue
            link_dict["from"] = PdfDocument._transform_rect(rect, src_page.rect, placement.target_rect)
            out_page.insert_link(link_dict)

    @staticmethod
    def _transform_rect(rect: fitz.Rect, source_rect: fitz.Rect, target_rect: fitz.Rect) -> fitz.Rect:
        factor_x = target_rect.width / source_rect.width
        factor_y = target_rect.height / source_rect.height
        return fitz.Rect(
            target_rect.x0 + (rect.x0 - source_rect.x0) * factor_x,
            target_rect.y0 + (rect.y0 - source_rect.y0) * factor_y,
            target_rect.x0 + (rect.x1 - source_rect.x0) * factor_x,
            target_rect.y0 + (rect.y1 - source_rect.y0) * factor_y,
        )
