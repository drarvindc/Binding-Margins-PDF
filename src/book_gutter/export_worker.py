from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore

from .pdf_document import ExportResult, PdfDocument, PdfDocumentError
from .pdf_transform import BindingSide, ShiftSettings


@dataclass(frozen=True)
class ExportSettings:
    output_path: Path
    scale: float
    shift_settings: ShiftSettings
    binding_side: BindingSide
    page_indices: tuple[int, ...]
    append_blank_partner: bool


class ExportWorker(QtCore.QObject):
    progress_changed = QtCore.Signal(int, int)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    cancelled = QtCore.Signal()

    def __init__(self, pdf_document: PdfDocument, settings: ExportSettings):
        super().__init__()
        self._pdf_document = pdf_document
        self._settings = settings

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self._pdf_document.export_pages(
                output_path=self._settings.output_path,
                page_indices=self._settings.page_indices,
                scale=self._settings.scale,
                shift_spec=self._settings.shift_settings,
                binding_side=self._settings.binding_side,
                append_blank_partner=self._settings.append_blank_partner,
                progress_callback=self.progress_changed.emit,
                cancel_check=QtCore.QThread.currentThread().isInterruptionRequested,
            )
            self.finished.emit(result)
        except PdfDocumentError as exc:
            message = str(exc)
            if "cancelled" in message.lower():
                self.cancelled.emit()
            else:
                self.failed.emit(message)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(str(exc))
