from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import fitz

from .content_bounds import ContentBoundsEstimate, estimate_content_bounds
from .pdf_transform import BindingSide, ShiftSpec, placement_for_page


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
    source_pages_exported: tuple[int, ...]
    blank_partner_added: bool
    blank_pages_added: int = 0


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

    def preview_pixmap(self, page_index: int, scale: float, shift_spec: ShiftSpec, binding_side: BindingSide, show_original: bool, dpi: int = 110) -> fitz.Pixmap:
        page = self._doc[page_index]
        return page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)

    def content_estimate(self, page_index: int) -> ContentBoundsEstimate:
        return estimate_content_bounds(self._doc[page_index])

    def export(
        self,
        output_path: Path,
        scale: float,
        shift_spec: ShiftSpec,
        binding_side: BindingSide,
        add_blank_final_page: bool,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExportResult:
        append_blank_partner = add_blank_final_page and self._doc.page_count % 2 == 1
        return self.export_pages(
            output_path=output_path,
            page_indices=tuple(range(self._doc.page_count)),
            scale=scale,
            shift_spec=shift_spec,
            binding_side=binding_side,
            append_blank_partner=append_blank_partner,
            blank_page_count=1 if append_blank_partner else 0,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def export_pages(
        self,
        output_path: Path,
        page_indices: Sequence[int],
        scale: float,
        shift_spec: ShiftSpec,
        binding_side: BindingSide,
        append_blank_partner: bool = False,
        blank_page_count: int | None = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExportResult:
        if self.path.resolve(strict=False) == output_path.resolve(strict=False):
            raise PdfDocumentError("The output file must be different from the source file.")
        if not page_indices:
            raise PdfDocumentError("No pages were selected for export.")
        if blank_page_count is None:
            blank_page_count = 1 if append_blank_partner else 0
        if blank_page_count < 0:
            raise PdfDocumentError("The selected page range is invalid.")

        normalized_indices = tuple(page_indices)
        for page_index in normalized_indices:
            if page_index < 0 or page_index >= self._doc.page_count:
                raise PdfDocumentError("The selected page range is outside the source document.")

        out_doc = fitz.open()
        temp_output = output_path.with_suffix(output_path.suffix + ".tmp")
        source_pages_exported = tuple(index + 1 for index in normalized_indices)
        total_pages = len(normalized_indices) + blank_page_count
        pages_written = 0
        blank_added = 0
        try:
            for out_index, page_index in enumerate(normalized_indices, start=1):
                if cancel_check and cancel_check():
                    raise PdfDocumentError("Export cancelled.")
                src_page = self._doc[page_index]
                out_page = out_doc.new_page(width=src_page.rect.width, height=src_page.rect.height)
                placement = placement_for_page(src_page.rect, scale, shift_spec, page_index, binding_side)
                out_page.show_pdf_page(placement.target_rect, self._doc, page_index, keep_proportion=True, clip=None, rotate=0)
                self._copy_links(src_page, out_page, placement)
                pages_written += 1
                if progress_callback:
                    progress_callback(out_index, total_pages)

            if blank_page_count:
                last_page = self._doc[normalized_indices[-1]]
                for blank_index in range(blank_page_count):
                    if cancel_check and cancel_check():
                        raise PdfDocumentError("Export cancelled.")
                    out_doc.new_page(width=last_page.rect.width, height=last_page.rect.height)
                    pages_written += 1
                    blank_added += 1
                    if progress_callback:
                        progress_callback(len(normalized_indices) + blank_index + 1, total_pages)

            out_doc.save(temp_output, garbage=4, deflate=True, clean=True)
            temp_output.replace(output_path)
            return ExportResult(
                output_path=output_path,
                pages_written=pages_written,
                blank_page_added=blank_added > 0,
                source_pages_exported=source_pages_exported,
                blank_partner_added=blank_added > 0,
                blank_pages_added=blank_added,
            )
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
