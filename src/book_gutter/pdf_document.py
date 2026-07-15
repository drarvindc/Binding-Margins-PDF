from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

import fitz

from .content_bounds import ContentBoundsEstimate, estimate_content_bounds
from .document_layout import DocumentComposition, DocumentLayout, OutputItem, OutputItemKind
from .page_side import PageSide
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
    source_pages_exported: tuple[int, ...]
    blank_pages_added: int = 0
    intentional_blank_pages_added: int = 0
    automatic_final_blank_pages_added: int = 0
    test_padding_blank_pages_added: int = 0
    blank_page_added: bool = False
    blank_partner_added: bool = False


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

    def compose(self, layout: DocumentLayout) -> DocumentComposition:
        page_sizes = [(page.rect.width, page.rect.height) for page in self._doc]
        return layout.compose(page_sizes)

    def export(
        self,
        output_path: Path,
        scale: float,
        shift_spec: ShiftSpec,
        binding_side: BindingSide,
        add_blank_final_page: bool,
        layout: DocumentLayout | None = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExportResult:
        layout = layout or DocumentLayout()
        composition = self.compose(layout)
        items = list(composition.items)
        if add_blank_final_page and len(items) % 2 == 1:
            last_item = items[-1]
            items.append(
                OutputItem(
                    kind=OutputItemKind.AUTOMATIC_FINAL_BLANK,
                    output_position=len(items) + 1,
                    side=layout.side_for_output_position(len(items) + 1, layout.first_page_side),
                    page_width_pt=last_item.page_width_pt,
                    page_height_pt=last_item.page_height_pt,
                )
            )
        return self.export_items(
            output_path=output_path,
            items=tuple(items),
            scale=scale,
            shift_spec=shift_spec,
            binding_side=binding_side,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def export_items(
        self,
        output_path: Path,
        items: Sequence[OutputItem],
        scale: float,
        shift_spec: ShiftSpec,
        binding_side: BindingSide,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExportResult:
        if self.path.resolve(strict=False) == output_path.resolve(strict=False):
            raise PdfDocumentError("The output file must be different from the source file.")
        if not items:
            raise PdfDocumentError("No pages were selected for export.")

        out_doc = fitz.open()
        temp_output = output_path.with_suffix(output_path.suffix + ".tmp")
        normalized_items = tuple(items)
        for item in normalized_items:
            if item.is_source_page:
                if item.source_page_index is None or item.source_page_index < 0 or item.source_page_index >= self._doc.page_count:
                    raise PdfDocumentError("The selected page range is outside the source document.")
        source_pages_exported = tuple(item.source_page_number for item in normalized_items if item.is_source_page and item.source_page_number is not None)
        intentional_blank_pages_added = sum(1 for item in normalized_items if item.kind == OutputItemKind.INTENTIONAL_BLANK)
        automatic_final_blank_pages_added = sum(1 for item in normalized_items if item.kind == OutputItemKind.AUTOMATIC_FINAL_BLANK)
        test_padding_blank_pages_added = sum(1 for item in normalized_items if item.kind == OutputItemKind.TEST_PADDING_BLANK)
        blank_pages_added = intentional_blank_pages_added + automatic_final_blank_pages_added + test_padding_blank_pages_added
        total_pages = len(normalized_items)
        pages_written = 0
        try:
            for out_index, item in enumerate(normalized_items, start=1):
                if cancel_check and cancel_check():
                    raise PdfDocumentError("Export cancelled.")
                if item.is_source_page:
                    src_page = self._doc[item.source_page_index]
                    out_page = out_doc.new_page(width=src_page.rect.width, height=src_page.rect.height)
                    placement = placement_for_page(src_page.rect, scale, shift_spec, item.side, binding_side)
                    out_page.show_pdf_page(placement.target_rect, self._doc, item.source_page_index, keep_proportion=True, clip=None, rotate=0)
                    self._copy_links(src_page, out_page, placement)
                else:
                    out_doc.new_page(width=item.page_width_pt, height=item.page_height_pt)
                pages_written += 1
                if progress_callback:
                    progress_callback(out_index, total_pages)

            out_doc.save(temp_output, garbage=4, deflate=True, clean=True)
            temp_output.replace(output_path)
            return ExportResult(
                output_path=output_path,
                pages_written=pages_written,
                source_pages_exported=source_pages_exported,
                blank_pages_added=blank_pages_added,
                intentional_blank_pages_added=intentional_blank_pages_added,
                automatic_final_blank_pages_added=automatic_final_blank_pages_added,
                test_padding_blank_pages_added=test_padding_blank_pages_added,
                blank_page_added=blank_pages_added > 0,
                blank_partner_added=automatic_final_blank_pages_added > 0,
            )
        except Exception:
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
            raise
        finally:
            out_doc.close()

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
        if blank_page_count is None:
            blank_page_count = 1 if append_blank_partner else 0
        items: list[OutputItem] = []
        for out_position, page_index in enumerate(page_indices, start=1):
            if page_index < 0 or page_index >= self._doc.page_count:
                raise PdfDocumentError("The selected page range is outside the source document.")
            page = self._doc[page_index]
            side = PageSide.RIGHT_ODD if (page_index + 1) % 2 == 1 else PageSide.LEFT_EVEN
            items.append(
                OutputItem(
                    kind=OutputItemKind.SOURCE_PAGE,
                    output_position=out_position,
                    side=side,
                    page_width_pt=page.rect.width,
                    page_height_pt=page.rect.height,
                    source_page_index=page_index,
                    source_page_number=page_index + 1,
                )
            )
        if blank_page_count:
            last_item = items[-1]
            for index in range(blank_page_count):
                items.append(
                    OutputItem(
                        kind=OutputItemKind.AUTOMATIC_FINAL_BLANK,
                        output_position=len(items) + 1,
                        side=PageSide.RIGHT_ODD if len(items) % 2 == 0 else PageSide.LEFT_EVEN,
                        page_width_pt=last_item.page_width_pt,
                        page_height_pt=last_item.page_height_pt,
                    )
                )
        return self.export_items(
            output_path=output_path,
            items=tuple(items),
            scale=scale,
            shift_spec=shift_spec,
            binding_side=binding_side,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

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
