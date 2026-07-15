from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .content_bounds import estimate_content_bounds, transformed_content_crosses_edge, transformed_margins
from .export_worker import ExportSettings, ExportWorker
from .logging_config import configure_logging
from .pdf_document import PdfDocument, PdfDocumentError
from .pdf_transform import BindingSide, is_odd_page, page_shift_sign, placement_for_page
from .preview_widget import PagePreviewWidget, PreviewState
from .units import format_mm, format_pct, points_to_mm


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Book Gutter PDF")
        self.setAcceptDrops(True)
        self._log_file = configure_logging()
        self._pdf: PdfDocument | None = None
        self._export_thread: QtCore.QThread | None = None
        self._export_worker: ExportWorker | None = None
        self._current_output_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        self.open_button = QtWidgets.QPushButton("Open PDF")
        self.export_button = QtWidgets.QPushButton("Create Print-Ready PDF")
        self.cancel_button = QtWidgets.QPushButton("Cancel Export")
        self.cancel_button.setEnabled(False)
        self.open_output_button = QtWidgets.QPushButton("Open Output Folder")
        self.open_output_button.setEnabled(False)

        self.file_label = QtWidgets.QLabel("No file open")
        self.page_count_label = QtWidgets.QLabel("-")
        self.page_size_label = QtWidgets.QLabel("-")
        self.mixed_label = QtWidgets.QLabel("-")

        self.binding_combo = QtWidgets.QComboBox()
        self.binding_combo.addItems(["Left binding", "Right binding"])
        self.shift_spin = QtWidgets.QDoubleSpinBox()
        self.shift_spin.setRange(0.0, 25.0)
        self.shift_spin.setSingleStep(0.5)
        self.shift_spin.setValue(5.0)
        self.shift_spin.setSuffix(" mm")

        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(80.0, 100.0)
        self.scale_spin.setSingleStep(0.5)
        self.scale_spin.setValue(100.0)
        self.scale_spin.setSuffix(" %")

        self.blank_check = QtWidgets.QCheckBox("Add blank final page")
        self.blank_check.setChecked(True)
        self.show_original_check = QtWidgets.QCheckBox("Show original position")

        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setEnabled(False)
        self.prev_button = QtWidgets.QPushButton("Previous")
        self.next_button = QtWidgets.QPushButton("Next")

        self.preview = PagePreviewWidget()

        self.current_page_label = QtWidgets.QLabel("-")
        self.shift_direction_label = QtWidgets.QLabel("-")
        self.scale_label = QtWidgets.QLabel("-")
        self.outer_margin_label = QtWidgets.QLabel("Estimated outer margins: -")
        self.warning_label = QtWidgets.QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #8a1c1c;")

        form = QtWidgets.QFormLayout()
        form.addRow("Binding side", self.binding_combo)
        form.addRow("Mirrored horizontal shift", self.shift_spin)
        form.addRow("Scale", self.scale_spin)
        form.addRow("", self.blank_check)
        form.addRow("", self.show_original_check)

        nav = QtWidgets.QHBoxLayout()
        nav.addWidget(self.prev_button)
        nav.addWidget(self.page_spin)
        nav.addWidget(self.next_button)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.open_button)
        top.addWidget(self.export_button)
        top.addWidget(self.cancel_button)
        top.addWidget(self.open_output_button)
        top.addStretch(1)

        meta = QtWidgets.QFormLayout()
        meta.addRow("File", self.file_label)
        meta.addRow("Pages", self.page_count_label)
        meta.addRow("Page size", self.page_size_label)
        meta.addRow("Mixed sizes", self.mixed_label)

        info = QtWidgets.QVBoxLayout()
        info.addLayout(meta)
        info.addWidget(self.current_page_label)
        info.addWidget(self.shift_direction_label)
        info.addWidget(self.scale_label)
        info.addWidget(self.outer_margin_label)
        info.addWidget(self.warning_label)
        info.addStretch(1)

        left = QtWidgets.QVBoxLayout()
        left.addLayout(top)
        left.addLayout(form)
        left.addLayout(nav)
        left.addLayout(info)
        left.addStretch(1)

        splitter = QtWidgets.QSplitter()
        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root = QtWidgets.QVBoxLayout(central)
        root.addWidget(splitter)

        self.open_button.clicked.connect(self.open_pdf)
        self.export_button.clicked.connect(self.export_pdf)
        self.cancel_button.clicked.connect(self.cancel_export)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.binding_combo.currentIndexChanged.connect(self.refresh_preview)
        self.shift_spin.valueChanged.connect(self.refresh_preview)
        self.scale_spin.valueChanged.connect(self.refresh_preview)
        self.blank_check.stateChanged.connect(self.refresh_preview)
        self.show_original_check.stateChanged.connect(self.refresh_preview)
        self.page_spin.valueChanged.connect(self.refresh_preview)
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.warning_label.setText(message)
        self.warning_label.setStyleSheet("color: #8a1c1c;" if error else "color: #2b6f36;")

    def _close_pdf(self) -> None:
        if self._pdf:
            self._pdf.close()
            self._pdf = None

    def open_pdf(self) -> None:
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf)")
        if not file_name:
            return
        self.load_pdf(Path(file_name))

    def load_pdf(self, path: Path) -> None:
        try:
            self._close_pdf()
            self._pdf = PdfDocument(path)
            info = self._pdf.info()
        except PdfDocumentError as exc:
            logging.exception("Failed to open PDF")
            QtWidgets.QMessageBox.critical(self, "Open PDF", str(exc))
            return

        self.file_label.setText(info.file_name)
        self.page_count_label.setText(str(info.page_count))
        sizes = {f"{round(w / 72.0 * 25.4, 1)} x {round(h / 72.0 * 25.4, 1)} mm" for w, h in info.page_sizes}
        self.page_size_label.setText(", ".join(sorted(sizes)))
        self.mixed_label.setText("Yes" if info.mixed_page_sizes else "No")
        self.page_spin.setEnabled(True)
        self.page_spin.setMaximum(info.page_count)
        self.page_spin.setValue(1)
        self.open_output_button.setEnabled(False)
        self.refresh_preview()

    def _selected_binding_side(self) -> BindingSide:
        return BindingSide.LEFT if self.binding_combo.currentIndex() == 0 else BindingSide.RIGHT

    def _current_page_index(self) -> int:
        return max(0, self.page_spin.value() - 1)

    def refresh_preview(self) -> None:
        if not self._pdf:
            self.preview.set_state(None)
            return
        page_index = self._current_page_index()
        page = self._pdf.document[page_index]
        estimate = estimate_content_bounds(page)
        placement = placement_for_page(page.rect, self.scale_spin.value(), self.shift_spin.value(), page_index, self._selected_binding_side())
        target = placement.target_rect
        content_after = transformed_margins(page, estimate, self.scale_spin.value(), self.shift_spin.value(), self._selected_binding_side(), page_index)
        crossing = transformed_content_crosses_edge(page, estimate, self.scale_spin.value(), self.shift_spin.value(), self._selected_binding_side(), page_index)
        if estimate.margins:
            self.outer_margin_label.setText(
                "Estimated outer margins: "
                f"left {format_mm(estimate.margins.left_mm)}, right {format_mm(estimate.margins.right_mm)}, "
                f"top {format_mm(estimate.margins.top_mm)}, bottom {format_mm(estimate.margins.bottom_mm)}"
            )
        else:
            self.outer_margin_label.setText("Estimated outer margins: no visible content detected")
        if content_after:
            outer = min(content_after.left_mm, content_after.right_mm)
            if crossing:
                self._set_status("The page canvas extends beyond the output edge. Visible content may be clipped on this page.", True)
            elif outer < 3.0:
                self._set_status("The page canvas extends beyond the output edge. Possible clipping risk: estimated outer content margin is below 3 mm.", True)
            elif placement.outer_warning:
                self._set_status("The page canvas extends beyond the output edge. Check the preview for actual content clipping.", False)
            else:
                self._set_status("")
        else:
            self._set_status("")
        pixmap = self._pdf.preview_pixmap(page_index, self.scale_spin.value(), self.shift_spin.value(), self._selected_binding_side(), self.show_original_check.isChecked())
        state = PreviewState(
            page_index=page_index,
            page_count=self._pdf.document.page_count,
            scale=self.scale_spin.value(),
            shift_mm=self.shift_spin.value(),
            binding_side=self._selected_binding_side(),
            show_original=self.show_original_check.isChecked(),
            page_rect=page.rect,
            target_rect=target,
            pixmap=pixmap,
            content_estimate=estimate,
        )
        self.current_page_label.setText(f"Current page: {page_index + 1} ({'odd' if is_odd_page(page_index) else 'even'})")
        self.shift_direction_label.setText(f"Shift direction: {'right' if page_shift_sign(page_index, self._selected_binding_side()) > 0 else 'left'}")
        self.scale_label.setText(f"Scale: {format_pct(self.scale_spin.value(), 1)}")
        self.preview.set_state(state)

    def previous_page(self) -> None:
        if self.page_spin.value() > 1:
            self.page_spin.setValue(self.page_spin.value() - 1)

    def next_page(self) -> None:
        if self._pdf and self.page_spin.value() < self._pdf.document.page_count:
            self.page_spin.setValue(self.page_spin.value() + 1)

    def _output_suggestion(self) -> Path | None:
        if not self._pdf:
            return None
        src = self._pdf.path
        shift_text = f"{self.shift_spin.value():.1f}".rstrip("0").rstrip(".")
        scale_text = f"{self.scale_spin.value():.1f}".rstrip("0").rstrip(".")
        suffix = f"_GUTTER_{shift_text}mm_{scale_text}pct.pdf"
        return src.with_name(src.stem + suffix)

    def export_pdf(self) -> None:
        if not self._pdf:
            QtWidgets.QMessageBox.information(self, "Export", "Open a PDF first.")
            return
        default_name = self._output_suggestion()
        file_name, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Create Print-Ready PDF", str(default_name), "PDF files (*.pdf)")
        if not file_name:
            return
        output_path = Path(file_name)
        if self._pdf.path.resolve(strict=False) == output_path.resolve(strict=False):
            QtWidgets.QMessageBox.warning(self, "Export", "The output file must be different from the source file.")
            return
        settings = ExportSettings(
            output_path=output_path,
            scale=self.scale_spin.value(),
            shift_mm=self.shift_spin.value(),
            binding_side=self._selected_binding_side(),
            add_blank_final_page=self.blank_check.isChecked(),
        )
        self.export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._export_thread = QtCore.QThread(self)
        self._export_worker = ExportWorker(self._pdf, settings)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress_changed.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.cancelled.connect(self._on_export_cancelled)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_worker.cancelled.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._cleanup_export)
        self._export_thread.start()

    def _on_export_progress(self, current: int, total: int) -> None:
        self.statusBar().showMessage(f"Exporting page {current} of {total}")

    def _cleanup_export(self) -> None:
        self.export_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._export_worker = None
        self._export_thread = None

    def _on_export_finished(self, result: object) -> None:
        self._current_output_path = getattr(result, "output_path", None)
        self.open_output_button.setEnabled(True)
        self.statusBar().showMessage("Export complete", 5000)
        QtWidgets.QMessageBox.information(
            self,
            "Export complete",
            f"Output: {result.output_path}\nPages written: {result.pages_written}\nBlank page added: {'Yes' if result.blank_page_added else 'No'}",
        )

    def _on_export_failed(self, message: str) -> None:
        logging.exception("Export failed: %s", message)
        QtWidgets.QMessageBox.critical(self, "Export failed", message)

    def _on_export_cancelled(self) -> None:
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("Export cancelled", 5000)

    def cancel_export(self) -> None:
        if self._export_thread is not None:
            self._export_thread.requestInterruption()

    def open_output_folder(self) -> None:
        if not self._current_output_path:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._current_output_path.parent)))

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # pragma: no cover - Qt event
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # pragma: no cover - Qt event
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.load_pdf(Path(url.toLocalFile()))
                event.acceptProposedAction()
                break


def run_app() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    return app.exec()
