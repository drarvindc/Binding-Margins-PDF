from __future__ import annotations

import logging
import sys
from pathlib import Path

import fitz
from PySide6 import QtCore, QtGui, QtWidgets

from .content_bounds import estimate_content_bounds, transformed_content_crosses_edge, transformed_margins
from .export_selection import (
    ExportSelection,
    current_page_pair_selection,
    custom_page_range_selection,
    suggest_full_export_filename,
    suggest_test_export_filename,
)
from .export_worker import ExportSettings, ExportWorker
from .logging_config import configure_logging
from .pdf_document import PdfDocument, PdfDocumentError
from .pdf_transform import BindingSide, ShiftSettings, is_odd_page, page_shift_sign, placement_for_page
from .preview_pairing import (
    clamp_page_number,
    format_facing_indicator,
    next_facing_page_number,
    previous_facing_page_number,
    resolve_facing_spread,
)
from .preview_widget import PagePreviewWidget, PreviewMode, PreviewPage, PreviewState
from .units import format_mm, format_pct


class TestExportDialog(QtWidgets.QDialog):
    def __init__(self, current_page: int, page_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Test PDF")
        self._current_page = current_page
        self._page_count = page_count

        self.current_pair_radio = QtWidgets.QRadioButton("Current page pair")
        self.custom_range_radio = QtWidgets.QRadioButton("Custom page range")
        self.current_pair_radio.setChecked(True)

        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setRange(1, page_count)
        self.start_spin.setValue(max(1, current_page))

        self.end_spin = QtWidgets.QSpinBox()
        self.end_spin.setRange(1, page_count)
        self.end_spin.setValue(min(page_count, current_page))

        self.expand_check = QtWidgets.QCheckBox("Expand range to complete duplex page pairs")
        self.expand_check.setChecked(True)

        self.open_folder_check = QtWidgets.QCheckBox("Open output folder after success")
        self.open_folder_check.setChecked(True)

        self.warning_label = QtWidgets.QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #8a1c1c;")

        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setWordWrap(True)

        pair_layout = QtWidgets.QVBoxLayout()
        pair_layout.addWidget(self.current_pair_radio)
        pair_layout.addWidget(self.custom_range_radio)

        range_form = QtWidgets.QFormLayout()
        range_form.addRow("Start page", self.start_spin)
        range_form.addRow("End page", self.end_spin)

        controls = QtWidgets.QVBoxLayout()
        controls.addLayout(pair_layout)
        controls.addLayout(range_form)
        controls.addWidget(self.expand_check)
        controls.addWidget(self.open_folder_check)
        controls.addWidget(self.warning_label)
        controls.addWidget(self.summary_label)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(controls)
        root.addWidget(buttons)

        self.current_pair_radio.toggled.connect(self._update_state)
        self.custom_range_radio.toggled.connect(self._update_state)
        self.start_spin.valueChanged.connect(self._sync_end_minimum)
        self.start_spin.valueChanged.connect(self._update_state)
        self.end_spin.valueChanged.connect(self._update_state)
        self.expand_check.toggled.connect(self._update_state)

        self._sync_end_minimum()
        self._update_state()

    def _sync_end_minimum(self, *_args) -> None:
        self.end_spin.setMinimum(self.start_spin.value())

    def _update_state(self, *_args) -> None:
        custom = self.custom_range_radio.isChecked()
        self.start_spin.setEnabled(custom)
        self.end_spin.setEnabled(custom)
        self.expand_check.setEnabled(custom)
        if custom:
            try:
                _, warning = custom_page_range_selection(self.start_spin.value(), self.end_spin.value(), self._page_count, self.expand_check.isChecked())
                if warning and self.expand_check.isChecked() and self.start_spin.value() % 2 == 0:
                    warning = warning + " The range will be expanded to include the preceding odd page."
                self.warning_label.setText(warning or "")
                self.summary_label.setText("")
                self.warning_label.setStyleSheet("color: #8a1c1c;" if warning else "color: #2b6f36;")
            except ValueError as exc:
                self.warning_label.setText(str(exc))
                self.warning_label.setStyleSheet("color: #8a1c1c;")
                self.summary_label.setText("")
        else:
            selection = current_page_pair_selection(self._current_page, self._page_count)
            self.warning_label.setText("")
            self.summary_label.setText(f"Selected: {selection.description}")
            self.warning_label.setStyleSheet("color: #8a1c1c;")

    def _accept(self) -> None:
        if self.custom_range_radio.isChecked() and self.start_spin.value() > self.end_spin.value():
            QtWidgets.QMessageBox.warning(self, "Create Test PDF", "The start page must not be after the end page.")
            return
        self.accept()

    def selection(self) -> tuple[ExportSelection, str | None]:
        if self.current_pair_radio.isChecked():
            return current_page_pair_selection(self._current_page, self._page_count), None
        return custom_page_range_selection(self.start_spin.value(), self.end_spin.value(), self._page_count, self.expand_check.isChecked())

    def open_folder_after_success(self) -> bool:
        return self.open_folder_check.isChecked()


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
        self.test_export_button = QtWidgets.QPushButton("Create Test PDF")
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

        self.same_shift_check = QtWidgets.QCheckBox("Use same shift for odd and even pages")
        self.same_shift_check.setChecked(True)

        self.odd_shift_spin = QtWidgets.QDoubleSpinBox()
        self.odd_shift_spin.setRange(0.0, 25.0)
        self.odd_shift_spin.setSingleStep(0.5)
        self.odd_shift_spin.setValue(5.0)
        self.odd_shift_spin.setSuffix(" mm")

        self.even_shift_spin = QtWidgets.QDoubleSpinBox()
        self.even_shift_spin.setRange(0.0, 25.0)
        self.even_shift_spin.setSingleStep(0.5)
        self.even_shift_spin.setValue(5.0)
        self.even_shift_spin.setSuffix(" mm")

        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(80.0, 100.0)
        self.scale_spin.setSingleStep(0.5)
        self.scale_spin.setValue(100.0)
        self.scale_spin.setSuffix(" %")

        self.blank_check = QtWidgets.QCheckBox("Add blank final page")
        self.blank_check.setChecked(True)
        self.preview_mode_combo = QtWidgets.QComboBox()
        self.preview_mode_combo.addItems(["Single Page", "Facing Pages"])
        self.preview_mode_combo.setCurrentIndex(0)
        self.show_binding_space_check = QtWidgets.QCheckBox("Show binding space")
        self.show_binding_space_check.setChecked(True)
        self.show_original_check = QtWidgets.QCheckBox("Show original position")

        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setEnabled(False)
        self.prev_button = QtWidgets.QPushButton("Previous")
        self.next_button = QtWidgets.QPushButton("Next")

        self.preview = PagePreviewWidget()

        self.current_page_label = QtWidgets.QLabel("-")
        self.shift_mode_label = QtWidgets.QLabel("-")
        self.shift_value_label = QtWidgets.QLabel("-")
        self.shift_direction_label = QtWidgets.QLabel("-")
        self.scale_label = QtWidgets.QLabel("-")
        self.content_margin_label = QtWidgets.QLabel("Estimated margins: -")
        self.warning_label = QtWidgets.QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #8a1c1c;")

        form = QtWidgets.QFormLayout()
        form.addRow("Binding side", self.binding_combo)
        form.addRow("", self.same_shift_check)
        form.addRow("Odd-page shift", self.odd_shift_spin)
        form.addRow("Even-page shift", self.even_shift_spin)
        form.addRow("Scale", self.scale_spin)
        form.addRow("Preview mode", self.preview_mode_combo)
        form.addRow("", self.show_binding_space_check)
        form.addRow("", self.blank_check)
        form.addRow("", self.show_original_check)

        nav = QtWidgets.QHBoxLayout()
        nav.addWidget(self.prev_button)
        nav.addWidget(self.page_spin)
        nav.addWidget(self.next_button)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.open_button)
        top.addWidget(self.export_button)
        top.addWidget(self.test_export_button)
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
        info.addWidget(self.shift_mode_label)
        info.addWidget(self.shift_value_label)
        info.addWidget(self.shift_direction_label)
        info.addWidget(self.scale_label)
        info.addWidget(self.content_margin_label)
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
        self.test_export_button.clicked.connect(self.export_test_pdf)
        self.cancel_button.clicked.connect(self.cancel_export)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.binding_combo.currentIndexChanged.connect(self.refresh_preview)
        self.same_shift_check.toggled.connect(self._sync_shift_controls)
        self.odd_shift_spin.valueChanged.connect(self._odd_shift_changed)
        self.even_shift_spin.valueChanged.connect(self.refresh_preview)
        self.scale_spin.valueChanged.connect(self.refresh_preview)
        self.blank_check.stateChanged.connect(self.refresh_preview)
        self.show_original_check.stateChanged.connect(self.refresh_preview)
        self.preview_mode_combo.currentIndexChanged.connect(self._preview_mode_changed)
        self.show_binding_space_check.stateChanged.connect(self.refresh_preview)
        self.page_spin.valueChanged.connect(self.refresh_preview)
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)
        self.preview.page_clicked.connect(self._set_active_page)

        self._sync_shift_controls(self.same_shift_check.isChecked())
        self._update_navigation_labels()

    def _sync_shift_controls(self, same: bool) -> None:
        self.even_shift_spin.setEnabled(not same)
        if same:
            self.even_shift_spin.blockSignals(True)
            self.even_shift_spin.setValue(self.odd_shift_spin.value())
            self.even_shift_spin.blockSignals(False)
        self.refresh_preview()

    def _odd_shift_changed(self, value: float) -> None:
        if self.same_shift_check.isChecked():
            self.even_shift_spin.blockSignals(True)
            self.even_shift_spin.setValue(value)
            self.even_shift_spin.blockSignals(False)
        self.refresh_preview()

    def _selected_shifts(self) -> ShiftSettings:
        return ShiftSettings(odd_mm=self.odd_shift_spin.value(), even_mm=self.even_shift_spin.value())

    def _preview_mode(self) -> PreviewMode:
        return PreviewMode.SINGLE_PAGE if self.preview_mode_combo.currentIndex() == 0 else PreviewMode.FACING_PAGES

    def _preview_mode_changed(self, *_args) -> None:
        self._update_navigation_labels()
        self.refresh_preview()

    def _update_navigation_labels(self) -> None:
        if self._preview_mode() == PreviewMode.FACING_PAGES:
            self.prev_button.setText("Previous Spread")
            self.next_button.setText("Next Spread")
        else:
            self.prev_button.setText("Previous")
            self.next_button.setText("Next")

    def _set_active_page(self, page_number: int) -> None:
        if not self._pdf:
            return
        clamped = clamp_page_number(page_number, self._pdf.document.page_count)
        if self.page_spin.value() != clamped:
            self.page_spin.setValue(clamped)

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

    def _page_title(self, page_index: int, compact: bool) -> str:
        if compact:
            return "Odd / Right page" if is_odd_page(page_index) else "Even / Left page"
        return f"Page {page_index + 1}"

    def _page_summary_text(
        self,
        page_index: int,
        compact: bool,
        estimate,
        transformed,
        crossing: bool,
        placement,
    ) -> str:
        page_number = page_index + 1
        if compact:
            if transformed:
                outer = min(transformed.left_mm, transformed.right_mm)
                summary = f"Page {page_number}: estimated outer margin {format_mm(outer)}"
                if crossing or outer < 3.0 or placement.outer_warning:
                    summary += " - possible clipping risk"
                return summary
            return f"Page {page_number}: no visible content detected"

        if estimate.margins:
            original = estimate.margins
            if transformed:
                return (
                    "Original outer margins: "
                    f"left {format_mm(original.left_mm)}, right {format_mm(original.right_mm)}, "
                    f"top {format_mm(original.top_mm)}, bottom {format_mm(original.bottom_mm)}\n"
                    "Estimated outer margins after transformation: "
                    f"left {format_mm(transformed.left_mm)}, right {format_mm(transformed.right_mm)}, "
                    f"top {format_mm(transformed.top_mm)}, bottom {format_mm(transformed.bottom_mm)}"
                )
            return (
                "Original outer margins: "
                f"left {format_mm(original.left_mm)}, right {format_mm(original.right_mm)}, "
                f"top {format_mm(original.top_mm)}, bottom {format_mm(original.bottom_mm)}\n"
                "Estimated outer margins after transformation: no visible content detected"
            )
        return "Estimated margins: no visible content detected"

    def _page_warning_info(self, transformed, crossing: bool, placement) -> tuple[str | None, bool]:
        if not transformed:
            return None, False
        outer = min(transformed.left_mm, transformed.right_mm)
        if crossing:
            return "Visible content may be clipped on this page.", True
        if outer < 3.0:
            return "Possible clipping risk: estimated outer content margin is below 3 mm.", True
        if placement.outer_warning:
            return "The page canvas extends beyond the output edge. Check the preview for actual content clipping.", False
        return None, False

    def _real_preview_page(self, page_index: int, compact: bool) -> tuple[PreviewPage, tuple[str | None, bool]]:
        page = self._pdf.document[page_index]
        shifts = self._selected_shifts()
        binding_side = self._selected_binding_side()
        placement = placement_for_page(page.rect, self.scale_spin.value(), shifts, page_index, binding_side)
        estimate = estimate_content_bounds(page)
        transformed = transformed_margins(page, estimate, self.scale_spin.value(), shifts, binding_side, page_index)
        crossing = transformed_content_crosses_edge(page, estimate, self.scale_spin.value(), shifts, binding_side, page_index)
        warning = self._page_warning_info(transformed, crossing, placement)
        summary = self._page_summary_text(page_index, compact, estimate, transformed, crossing, placement)
        pixmap = self._pdf.preview_pixmap(page_index, self.scale_spin.value(), shifts, binding_side, self.show_original_check.isChecked())
        preview_page = PreviewPage(
            page_number=page_index + 1,
            page_index=page_index,
            page_rect=fitz.Rect(page.rect),
            target_rect=fitz.Rect(placement.target_rect),
            pixmap=pixmap,
            title_text=self._page_title(page_index, compact),
            summary_text=summary,
            is_placeholder=False,
        )
        return preview_page, warning

    @staticmethod
    def _placeholder_preview_page(reference_rect: fitz.Rect, title_text: str, summary_text: str) -> PreviewPage:
        return PreviewPage(
            page_number=None,
            page_index=None,
            page_rect=fitz.Rect(reference_rect),
            target_rect=None,
            pixmap=None,
            title_text=title_text,
            summary_text=summary_text,
            is_placeholder=True,
        )

    def _preview_note_text(self) -> str:
        notes: list[str] = []
        if self._preview_mode() == PreviewMode.FACING_PAGES:
            notes.append("Click a visible page to jump to it.")
        if self._pdf and self.blank_check.isChecked() and self._pdf.document.page_count % 2 == 1:
            notes.append("Full export will append a blank final page.")
        return "\n".join(notes)

    def refresh_preview(self, *_args) -> None:
        if not self._pdf:
            self.preview.set_state(None)
            self.current_page_label.setText("-")
            self.shift_mode_label.setText("-")
            self.shift_value_label.setText("-")
            self.shift_direction_label.setText("-")
            self.scale_label.setText("-")
            self.content_margin_label.setText("Estimated margins: -")
            self._set_status("")
            return
        page_count = self._pdf.document.page_count
        page_index = self._current_page_index()
        mode = self._preview_mode()
        compact = mode == PreviewMode.FACING_PAGES
        spread_warnings: list[str | None] = []

        if mode == PreviewMode.SINGLE_PAGE:
            pages = []
            page, warning_info = self._real_preview_page(page_index, compact=False)
            pages.append(page)
            warning_text, warning_error = warning_info
            page_label = f"Current page: {page_index + 1} ({'odd' if is_odd_page(page_index) else 'even'})"
        else:
            spread = resolve_facing_spread(page_index + 1, page_count)
            pages = []
            if spread.has_left_page:
                left_page, left_warning = self._real_preview_page(spread.left_page_number - 1, compact=True)
                pages.append(left_page)
                spread_warnings.append(left_warning)
            else:
                right_reference = self._pdf.document[spread.right_page_number - 1]
                pages.append(
                    self._placeholder_preview_page(
                        right_reference.rect,
                        "Inside cover / no facing page",
                        "No source page on this side.",
                    )
                )
            if spread.has_right_page:
                right_page, right_warning = self._real_preview_page(spread.right_page_number - 1, compact=True)
                pages.append(right_page)
                spread_warnings.append(right_warning)
            else:
                left_reference = self._pdf.document[spread.left_page_number - 1]
                pages.append(
                    self._placeholder_preview_page(
                        left_reference.rect,
                        "Blank / no source page",
                        "No source page on this side.",
                    )
                )
            page_label = f"Current spread: {format_facing_indicator(spread, page_count)}"

        active_page_index = page_index
        active_page = self._pdf.document[active_page_index]
        shifts = self._selected_shifts()
        placement = placement_for_page(active_page.rect, self.scale_spin.value(), shifts, active_page_index, self._selected_binding_side())
        estimate = estimate_content_bounds(active_page)
        transformed = transformed_margins(active_page, estimate, self.scale_spin.value(), shifts, self._selected_binding_side(), active_page_index)
        crossing = transformed_content_crosses_edge(active_page, estimate, self.scale_spin.value(), shifts, self._selected_binding_side(), active_page_index)
        active_warning_text, active_warning_error = self._page_warning_info(transformed, crossing, placement)
        warning_text = active_warning_text
        warning_error = active_warning_error
        if warning_text is None:
            for message, is_error in spread_warnings:
                if message:
                    warning_text = message
                    warning_error = is_error
                    break

        self.current_page_label.setText(page_label)
        self.shift_mode_label.setText(f"Preview mode: {'Facing pages' if mode == PreviewMode.FACING_PAGES else 'Single page'}")
        self.shift_value_label.setText(
            f"Odd shift: {format_mm(self.odd_shift_spin.value())}, even shift: {format_mm(self.even_shift_spin.value())}, active shift: {format_mm(placement.shift_mm)}"
        )
        self.shift_direction_label.setText(f"Shift direction: {'right' if page_shift_sign(active_page_index, self._selected_binding_side()) > 0 else 'left'}")
        self.scale_label.setText(f"Scale: {format_pct(self.scale_spin.value(), 1)}")
        self.content_margin_label.setText("\n".join(page.summary_text for page in pages))
        self._set_status(warning_text or "", warning_error)

        state = PreviewState(
            mode=mode,
            page_count=page_count,
            active_page_number=page_index + 1,
            indicator_text=format_facing_indicator(resolve_facing_spread(page_index + 1, page_count), page_count)
            if mode == PreviewMode.FACING_PAGES
            else f"Page {page_index + 1} of {page_count}",
            note_text=self._preview_note_text(),
            scale=self.scale_spin.value(),
            binding_side=self._selected_binding_side(),
            show_original_position=self.show_original_check.isChecked(),
            show_binding_space=self.show_binding_space_check.isChecked(),
            pages=tuple(pages),
        )
        self.preview.set_state(state)

    def previous_page(self) -> None:
        if not self._pdf:
            return
        current = self.page_spin.value()
        if self._preview_mode() == PreviewMode.FACING_PAGES:
            target = previous_facing_page_number(current, self._pdf.document.page_count)
        else:
            target = clamp_page_number(current - 1, self._pdf.document.page_count)
        self._set_active_page(target)

    def next_page(self) -> None:
        if not self._pdf:
            return
        current = self.page_spin.value()
        if self._preview_mode() == PreviewMode.FACING_PAGES:
            target = next_facing_page_number(current, self._pdf.document.page_count)
        else:
            target = clamp_page_number(current + 1, self._pdf.document.page_count)
        self._set_active_page(target)

    def _export_via_dialog(self, selection, suggested_filename: str, open_folder_after_success: bool) -> None:
        if not self._pdf:
            return
        default_name = self._pdf.path.with_name(suggested_filename)
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
            shift_settings=self._selected_shifts(),
            binding_side=self._selected_binding_side(),
            page_indices=selection.page_indices,
            append_blank_partner=selection.append_blank_partner,
        )
        self._start_export(settings, open_folder_after_success, test_export=True)

    def export_pdf(self) -> None:
        if not self._pdf:
            QtWidgets.QMessageBox.information(self, "Export", "Open a PDF first.")
            return
        suggested_name = suggest_full_export_filename(self._pdf.path, self._selected_shifts(), self.scale_spin.value())
        file_name, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Create Print-Ready PDF", str(self._pdf.path.with_name(suggested_name)), "PDF files (*.pdf)")
        if not file_name:
            return
        output_path = Path(file_name)
        if self._pdf.path.resolve(strict=False) == output_path.resolve(strict=False):
            QtWidgets.QMessageBox.warning(self, "Export", "The output file must be different from the source file.")
            return
        settings = ExportSettings(
            output_path=output_path,
            scale=self.scale_spin.value(),
            shift_settings=self._selected_shifts(),
            binding_side=self._selected_binding_side(),
            page_indices=tuple(range(self._pdf.document.page_count)),
            append_blank_partner=self.blank_check.isChecked() and self._pdf.document.page_count % 2 == 1,
        )
        self._start_export(settings, open_folder_after_success=False, test_export=False)

    def export_test_pdf(self) -> None:
        if not self._pdf:
            QtWidgets.QMessageBox.information(self, "Create Test PDF", "Open a PDF first.")
            return
        dialog = TestExportDialog(self.page_spin.value(), self._pdf.document.page_count, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selection, warning = dialog.selection()
        if warning:
            self._set_status(warning, True)
        suggested_name = suggest_test_export_filename(self._pdf.path, selection, self._selected_shifts(), self.scale_spin.value())
        self._export_via_dialog(selection, suggested_name, dialog.open_folder_after_success())

    def _start_export(self, settings: ExportSettings, open_folder_after_success: bool, test_export: bool) -> None:
        self.export_button.setEnabled(False)
        self.test_export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._export_thread = QtCore.QThread(self)
        self._export_worker = ExportWorker(self._pdf, settings)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress_changed.connect(self._on_export_progress)
        self._export_worker.finished.connect(lambda result: self._on_export_finished(result, open_folder_after_success, test_export))
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
        self.test_export_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._export_worker = None
        self._export_thread = None

    def _format_page_list(self, pages: tuple[int, ...]) -> str:
        if not pages:
            return "-"
        if len(pages) == 1:
            return str(pages[0])
        if list(pages) == list(range(pages[0], pages[-1] + 1)):
            return f"{pages[0]}-{pages[-1]}"
        return ", ".join(str(page) for page in pages)

    def _on_export_finished(self, result: object, open_folder_after_success: bool, test_export: bool) -> None:
        self._current_output_path = getattr(result, "output_path", None)
        self.open_output_button.setEnabled(True)
        self.statusBar().showMessage("Export complete", 5000)
        if test_export:
            source_pages = self._format_page_list(tuple(getattr(result, "source_pages_exported", ())))
            blank_text = "Yes" if getattr(result, "blank_partner_added", False) else "No"
            message = (
                f"Output: {result.output_path}\n"
                f"Pages written: {result.pages_written}\n"
                f"Source pages exported: {source_pages}\n"
                f"Blank partner added: {blank_text}"
            )
        else:
            message = (
                f"Output: {result.output_path}\n"
                f"Pages written: {result.pages_written}\n"
                f"Blank page added: {'Yes' if result.blank_page_added else 'No'}"
            )
        QtWidgets.QMessageBox.information(self, "Export complete", message)
        if open_folder_after_success and self._current_output_path is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._current_output_path.parent)))

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
