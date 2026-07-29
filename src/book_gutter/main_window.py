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
from .document_layout import BlankPlacement, DocumentComposition, DocumentLayout, OutputItem, OutputItemKind
from .export_worker import ExportSettings, ExportWorker
from .logging_config import configure_logging
from .pdf_document import PdfDocument, PdfDocumentError
from .page_side import PageSide
from .pdf_transform import BindingSide, ShiftSettings, page_shift_sign, placement_for_page
from .preview_pairing import format_facing_indicator, previous_output_position, next_output_position, resolve_facing_spread
from .preview_widget import PagePreviewWidget, PreviewMode, PreviewPage, PreviewState
from .units import format_mm, format_pct


class TestExportDialog(QtWidgets.QDialog):
    def __init__(self, current_page: int, composition: DocumentComposition, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Test PDF")
        self._current_page = current_page
        self._composition = composition
        self._page_count = len(composition.source_page_sizes)

        self.current_pair_radio = QtWidgets.QRadioButton("Two duplex sheets - 4 pages")
        self.custom_range_radio = QtWidgets.QRadioButton("Custom page range")
        self.current_pair_radio.setChecked(True)

        self.info_label = QtWidgets.QLabel("Exports two back-to-back sheets. The middle pages form a facing spread for checking both binding margins.")
        self.info_label.setWordWrap(True)
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setWordWrap(True)

        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setRange(1, self._page_count)
        self.start_spin.setValue(max(1, current_page))

        self.end_spin = QtWidgets.QSpinBox()
        self.end_spin.setRange(1, self._page_count)
        self.end_spin.setValue(min(self._page_count, current_page))

        self.expand_check = QtWidgets.QCheckBox("Expand range to complete duplex page pairs")
        self.expand_check.setChecked(True)

        self.open_folder_check = QtWidgets.QCheckBox("Open output folder after success")
        self.open_folder_check.setChecked(True)

        self.warning_label = QtWidgets.QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #8a1c1c;")

        pair_layout = QtWidgets.QVBoxLayout()
        pair_layout.addWidget(self.current_pair_radio)
        pair_layout.addWidget(self.custom_range_radio)

        range_form = QtWidgets.QFormLayout()
        range_form.addRow("Start page", self.start_spin)
        range_form.addRow("End page", self.end_spin)

        controls = QtWidgets.QVBoxLayout()
        controls.addWidget(self.info_label)
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
                _, warning = custom_page_range_selection(self.start_spin.value(), self.end_spin.value(), self._composition, self.expand_check.isChecked())
                if warning and self.expand_check.isChecked():
                    warning = warning + " The range will be expanded when possible."
                self.warning_label.setText(warning or "")
                self.summary_label.setText("")
                self.warning_label.setStyleSheet("color: #8a1c1c;" if warning else "color: #2b6f36;")
            except ValueError as exc:
                self.warning_label.setText(str(exc))
                self.warning_label.setStyleSheet("color: #8a1c1c;")
                self.summary_label.setText("")
        else:
            selection = current_page_pair_selection(self._current_page, self._composition)
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
            return current_page_pair_selection(self._current_page, self._composition), None
        return custom_page_range_selection(self.start_spin.value(), self.end_spin.value(), self._composition, self.expand_check.isChecked())

    def open_folder_after_success(self) -> bool:
        return self.open_folder_check.isChecked()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Book Gutter PDF")
        self.setAcceptDrops(True)
        self._log_file = configure_logging()
        self._pdf: PdfDocument | None = None
        self._layout = DocumentLayout()
        self._composition: DocumentComposition | None = None
        self._active_output_position = 1
        self._export_thread: QtCore.QThread | None = None
        self._export_worker: ExportWorker | None = None
        self._current_output_path: Path | None = None
        self._export_open_folder_after_success = False
        self._export_test_export = False
        self._export_test_selection_description = ""
        self._export_result_handled = False
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

        self.first_page_side_combo = QtWidgets.QComboBox()
        self.first_page_side_combo.addItems(["Right / Odd side", "Left / Even side"])
        self.first_page_side_combo.setCurrentIndex(0)

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
        self.show_binding_space_check = QtWidgets.QCheckBox("Show binding space")
        self.show_binding_space_check.setChecked(True)
        self.show_original_check = QtWidgets.QCheckBox("Show original position")

        self.insert_blank_before_button = QtWidgets.QPushButton("Insert blank before")
        self.insert_blank_after_button = QtWidgets.QPushButton("Insert blank after")
        self.blank_list = QtWidgets.QListWidget()
        self.blank_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.remove_blank_button = QtWidgets.QPushButton("Remove selected blank")

        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setEnabled(False)

        self.preview = PagePreviewWidget()
        self.preview_mode_group = QtWidgets.QButtonGroup(self)
        self.preview_mode_group.setExclusive(True)
        self.preview_mode_single_button = self._create_preview_mode_button("Single Page", self._preview_mode_icon(False))
        self.preview_mode_facing_button = self._create_preview_mode_button("Facing Pages", self._preview_mode_icon(True))
        self.preview_mode_group.addButton(self.preview_mode_single_button)
        self.preview_mode_group.addButton(self.preview_mode_facing_button)
        self.preview_mode_single_button.clicked.connect(lambda: self._set_preview_mode(PreviewMode.SINGLE_PAGE))
        self.preview_mode_facing_button.clicked.connect(lambda: self._set_preview_mode(PreviewMode.FACING_PAGES))

        self.prev_button = QtWidgets.QPushButton("Previous")
        self.next_button = QtWidgets.QPushButton("Next")
        self.preview_location_label = QtWidgets.QLabel("")
        self.preview_location_label.setObjectName("previewLocationLabel")
        self.preview_location_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_location_label.setStyleSheet("color: #5f5a52; font-weight: 600;")

        self.current_item_label = QtWidgets.QLabel("-")
        self.current_page_label = QtWidgets.QLabel("-")
        self.output_position_label = QtWidgets.QLabel("-")
        self.side_label = QtWidgets.QLabel("-")
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
        form.addRow("Source PDF page 1 appears on", self.first_page_side_combo)
        form.addRow("", self.same_shift_check)
        form.addRow("Odd-page shift", self.odd_shift_spin)
        form.addRow("Even-page shift", self.even_shift_spin)
        form.addRow("Scale", self.scale_spin)
        form.addRow("", self.show_binding_space_check)
        form.addRow("", self.blank_check)
        form.addRow("", self.show_original_check)

        blank_box = QtWidgets.QGroupBox("Inserted blanks")
        blank_box_layout = QtWidgets.QVBoxLayout(blank_box)
        blank_button_row = QtWidgets.QHBoxLayout()
        blank_button_row.addWidget(self.insert_blank_before_button)
        blank_button_row.addWidget(self.insert_blank_after_button)
        blank_button_row.addWidget(self.remove_blank_button)
        blank_box_layout.addLayout(blank_button_row)
        blank_box_layout.addWidget(self.blank_list)

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
        info.addWidget(self.current_item_label)
        info.addWidget(self.current_page_label)
        info.addWidget(self.output_position_label)
        info.addWidget(self.side_label)
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
        left.addWidget(blank_box)
        left.addLayout(info)
        left.addStretch(1)

        splitter = QtWidgets.QSplitter()
        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left)
        preview_panel = QtWidgets.QWidget()
        preview_panel_layout = QtWidgets.QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(0, 0, 0, 0)
        preview_panel_layout.setSpacing(10)

        preview_header = QtWidgets.QHBoxLayout()
        preview_header.setContentsMargins(2, 0, 2, 0)
        preview_header.setSpacing(8)
        preview_header.addWidget(self.preview_mode_single_button)
        preview_header.addWidget(self.preview_mode_facing_button)
        preview_header.addStretch(1)

        preview_footer = QtWidgets.QHBoxLayout()
        preview_footer.setContentsMargins(2, 0, 2, 0)
        preview_footer.setSpacing(8)
        preview_footer.addWidget(self.prev_button)
        preview_footer.addWidget(self.page_spin)
        preview_footer.addWidget(self.preview_location_label)
        preview_footer.addWidget(self.next_button)
        preview_footer.addStretch(1)

        preview_panel_layout.addLayout(preview_header)
        preview_panel_layout.addWidget(self.preview, 1)
        preview_panel_layout.addLayout(preview_footer)

        splitter.addWidget(left_widget)
        splitter.addWidget(preview_panel)
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
        self.first_page_side_combo.currentIndexChanged.connect(self.refresh_preview)
        self.same_shift_check.toggled.connect(self._sync_shift_controls)
        self.odd_shift_spin.valueChanged.connect(self._odd_shift_changed)
        self.even_shift_spin.valueChanged.connect(self.refresh_preview)
        self.scale_spin.valueChanged.connect(self.refresh_preview)
        self.blank_check.stateChanged.connect(self.refresh_preview)
        self.show_original_check.stateChanged.connect(self.refresh_preview)
        self.show_binding_space_check.stateChanged.connect(self.refresh_preview)
        self.page_spin.valueChanged.connect(self._source_page_changed)
        self.insert_blank_before_button.clicked.connect(self.insert_blank_before_current_page)
        self.insert_blank_after_button.clicked.connect(self.insert_blank_after_current_page)
        self.remove_blank_button.clicked.connect(self.remove_selected_blank)
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)
        self.preview.page_clicked.connect(self._set_active_source_page)

        self._sync_shift_controls(self.same_shift_check.isChecked())
        self._set_preview_mode(PreviewMode.SINGLE_PAGE)

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
        return PreviewMode.FACING_PAGES if self.preview_mode_facing_button.isChecked() else PreviewMode.SINGLE_PAGE

    def _create_preview_mode_button(self, text: str, icon: QtGui.QIcon) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText(text)
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(22, 16))
        button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setAutoRaise(False)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setObjectName(f"previewMode{''.join(part.title() for part in text.split())}Button")
        button.setStyleSheet(
            "QToolButton {"
            "  padding: 6px 10px;"
            "  border: 1px solid #c9c1b3;"
            "  border-radius: 8px;"
            "  background: #f7f3eb;"
            "}"
            "QToolButton:checked {"
            "  background: #dce8ff;"
            "  border-color: #4c7df0;"
            "}"
        )
        return button

    def _preview_mode_icon(self, facing: bool) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(26, 18)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor("#425466"), 1.8)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
        if facing:
            painter.drawRoundedRect(QtCore.QRectF(2, 2.5, 8.5, 13), 1.8, 1.8)
            painter.drawRoundedRect(QtCore.QRectF(15.5, 2.5, 8.5, 13), 1.8, 1.8)
        else:
            painter.drawRoundedRect(QtCore.QRectF(5, 2.5, 16, 13), 1.8, 1.8)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _set_preview_mode(self, mode: PreviewMode) -> None:
        self.preview_mode_single_button.blockSignals(True)
        self.preview_mode_facing_button.blockSignals(True)
        self.preview_mode_single_button.setChecked(mode == PreviewMode.SINGLE_PAGE)
        self.preview_mode_facing_button.setChecked(mode == PreviewMode.FACING_PAGES)
        self.preview_mode_single_button.blockSignals(False)
        self.preview_mode_facing_button.blockSignals(False)
        self.refresh_preview()

    def _first_page_side(self) -> PageSide:
        return PageSide.RIGHT_ODD if self.first_page_side_combo.currentIndex() == 0 else PageSide.LEFT_EVEN

    def _current_composition(self) -> DocumentComposition | None:
        return self._composition

    def _compose_layout(self) -> DocumentComposition | None:
        if not self._pdf:
            self._composition = None
            return None
        self._layout = self._layout.with_first_page_side(self._first_page_side())
        self._composition = self._pdf.compose(self._layout)
        return self._composition

    def _active_item(self) -> OutputItem | None:
        if not self._composition:
            return None
        if self._active_output_position < 1 or self._active_output_position > len(self._composition.items):
            return None
        return self._composition.item_at_output_position(self._active_output_position)

    def _set_active_output_position(self, output_position: int) -> None:
        if not self._composition:
            return
        clamped = max(1, min(output_position, len(self._composition.items)))
        self._active_output_position = clamped
        item = self._active_item()
        if item and item.is_source_page and item.source_page_number is not None and self.page_spin.value() != item.source_page_number:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(item.source_page_number)
            self.page_spin.blockSignals(False)
        elif item and item.kind == OutputItemKind.INTENTIONAL_BLANK and item.blank_reference_source_page_number is not None and self.page_spin.value() != item.blank_reference_source_page_number:
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(item.blank_reference_source_page_number)
            self.page_spin.blockSignals(False)
        self.refresh_preview()

    def _set_active_source_page(self, page_number: int) -> None:
        if not self._composition:
            return
        position = self._composition.output_position_for_source_page_number(page_number)
        if position is None:
            return
        self._set_active_output_position(position)

    def _source_page_changed(self, page_number: int) -> None:
        self._set_active_source_page(page_number)

    def _blank_label(self, item: OutputItem) -> str:
        if item.blank_placement == BlankPlacement.BEFORE:
            return f"Blank before source page {item.blank_reference_source_page_number}"
        if item.blank_placement == BlankPlacement.AFTER:
            return f"Blank after source page {item.blank_reference_source_page_number}"
        if item.kind == OutputItemKind.TEST_PADDING_BLANK:
            return "Test padding blank"
        if item.kind == OutputItemKind.AUTOMATIC_FINAL_BLANK:
            return "Automatic final blank"
        return "Blank page"

    def _refresh_blank_list(self) -> None:
        self.blank_list.clear()
        if not self._composition:
            return
        for item in self._composition.items:
            if item.kind != OutputItemKind.INTENTIONAL_BLANK:
                continue
            label = self._blank_label(item)
            list_item = QtWidgets.QListWidgetItem(label)
            list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item.blank_insertion_id)
            self.blank_list.addItem(list_item)

    def _selected_blank_insertion_id(self) -> int | None:
        item = self.blank_list.currentItem()
        if item is None:
            return None
        value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if value is None:
            return None
        return int(value)

    def _reselect_current_item(self) -> None:
        if not self._composition:
            return
        current_source = self.page_spin.value()
        if current_source > 0:
            position = self._composition.output_position_for_source_page_number(current_source)
            if position is not None:
                self._active_output_position = position
                return
        self._active_output_position = min(self._active_output_position, len(self._composition.items))

    def _insert_blank(self, placement: str) -> None:
        if not self._pdf:
            return
        source_page = self.page_spin.value()
        if placement == "before":
            self._layout = self._layout.add_blank_before(source_page)
        else:
            self._layout = self._layout.add_blank_after(source_page)
        self._compose_layout()
        self._reselect_current_item()
        self._refresh_blank_list()
        self.refresh_preview()

    def insert_blank_before_current_page(self) -> None:
        self._insert_blank("before")

    def insert_blank_after_current_page(self) -> None:
        self._insert_blank("after")

    def remove_selected_blank(self) -> None:
        insertion_id = self._selected_blank_insertion_id()
        if insertion_id is None:
            return
        self._layout = self._layout.remove_blank(insertion_id)
        self._compose_layout()
        self._reselect_current_item()
        self._refresh_blank_list()
        self.refresh_preview()

    def _set_status(self, message: str, error: bool = False) -> None:
        self.warning_label.setText(message)
        self.warning_label.setStyleSheet("color: #8a1c1c;" if error else "color: #2b6f36;")

    @staticmethod
    def _assert_gui_thread() -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if QtCore.QThread.currentThread() != app.thread():
            raise RuntimeError("Export UI handlers must run on the main Qt thread.")

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
        self._layout = DocumentLayout()
        self.first_page_side_combo.setCurrentIndex(0)
        self._composition = self._pdf.compose(self._layout)
        self._active_output_position = 1
        self.page_spin.setEnabled(True)
        self.page_spin.setMaximum(info.page_count)
        self.page_spin.setValue(1)
        self._refresh_blank_list()
        self.open_output_button.setEnabled(False)
        self.refresh_preview()

    def _selected_binding_side(self) -> BindingSide:
        return BindingSide.LEFT if self.binding_combo.currentIndex() == 0 else BindingSide.RIGHT

    def _source_page_count(self) -> int:
        if not self._composition:
            return 0
        return len(self._composition.source_page_sizes)

    def _source_page_index(self) -> int:
        return max(0, self.page_spin.value() - 1)

    def _page_item_title(self, item: OutputItem) -> str:
        if item.kind == OutputItemKind.SOURCE_PAGE and item.source_page_number is not None:
            return f"Source page {item.source_page_number} — {item.side.label}"
        if item.kind == OutputItemKind.INTENTIONAL_BLANK:
            return f"Inserted blank — {item.side.label}"
        if item.kind == OutputItemKind.AUTOMATIC_FINAL_BLANK:
            return f"Automatic final blank — {item.side.label}"
        if item.kind == OutputItemKind.TEST_PADDING_BLANK:
            return f"Test padding blank — {item.side.label}"
        return "Output item"

    def _preview_summary_text(self, item: OutputItem) -> str:
        return ""

    def _preview_footer_text(self, composition: DocumentComposition, active_item: OutputItem, mode: PreviewMode) -> str:
        if mode == PreviewMode.SINGLE_PAGE:
            if active_item.kind == OutputItemKind.SOURCE_PAGE and active_item.source_page_number is not None:
                return f"Page {active_item.source_page_number} of {len(composition.source_page_sizes)}"
            return f"Output {self._active_output_position} of {len(composition.items)}"

        spread = resolve_facing_spread(composition, self._active_output_position)
        source_items = [item for item in (spread.left_item, spread.right_item) if item is not None and item.source_page_number is not None]
        if len(source_items) >= 2:
            left = source_items[0].source_page_number
            right = source_items[-1].source_page_number
            return f"Pages {left}-{right} of {len(composition.source_page_sizes)}"
        if len(source_items) == 1:
            return f"Page {source_items[0].source_page_number} of {len(composition.source_page_sizes)}"
        if spread.left_item is not None:
            return f"Output {spread.left_item.output_position} of {len(composition.items)}"
        if spread.right_item is not None:
            return f"Output {spread.right_item.output_position} of {len(composition.items)}"
        return f"Output {self._active_output_position} of {len(composition.items)}"

    def _source_preview_page(self, item: OutputItem, compact: bool) -> tuple[PreviewPage, tuple[str | None, bool]]:
        if self._pdf is None or item.source_page_index is None:
            raise RuntimeError("A source page is required for this preview page.")
        page = self._pdf.document[item.source_page_index]
        shifts = self._selected_shifts()
        binding_side = self._selected_binding_side()
        placement = placement_for_page(page.rect, self.scale_spin.value(), shifts, item.side, binding_side)
        estimate = estimate_content_bounds(page)
        transformed = transformed_margins(page, estimate, self.scale_spin.value(), shifts, binding_side, item.side)
        crossing = transformed_content_crosses_edge(page, estimate, self.scale_spin.value(), shifts, binding_side, item.side)
        warning_text = None
        warning_error = False
        if transformed:
            outer = min(transformed.left_mm, transformed.right_mm)
            if crossing:
                warning_text = "Visible content may be clipped on this page."
                warning_error = True
            elif outer < 3.0:
                warning_text = "Possible clipping risk: estimated outer content margin is below 3 mm."
                warning_error = True
            elif placement.outer_warning:
                warning_text = "The page canvas extends beyond the output edge. Check the preview for actual content clipping."
        summary = ""

        pixmap = self._pdf.preview_pixmap(item.source_page_index, self.scale_spin.value(), shifts, binding_side, self.show_original_check.isChecked())
        preview_page = PreviewPage(
            page_number=item.source_page_number,
            page_index=item.source_page_index,
            page_rect=fitz.Rect(page.rect),
            target_rect=fitz.Rect(placement.target_rect),
            pixmap=pixmap,
            title_text=self._page_item_title(item),
            summary_text=summary,
            is_placeholder=False,
            page_side=item.side,
        )
        return preview_page, (warning_text, warning_error)

    def _blank_preview_page(self, item: OutputItem) -> PreviewPage:
        width = item.page_width_pt
        height = item.page_height_pt
        return PreviewPage(
            page_number=None,
            page_index=None,
            page_rect=fitz.Rect(0, 0, width, height),
            target_rect=None,
            pixmap=None,
            title_text=self._page_item_title(item),
            summary_text="",
            is_placeholder=False,
            page_side=item.side,
        )

    def _placeholder_preview_page(self, reference_rect: fitz.Rect, title_text: str, summary_text: str) -> PreviewPage:
        return PreviewPage(
            page_number=None,
            page_index=None,
            page_rect=fitz.Rect(reference_rect),
            target_rect=None,
            pixmap=None,
            title_text=title_text,
            summary_text="",
            is_placeholder=True,
        )

    def _preview_note_text(self) -> str:
        notes: list[str] = []
        if self._preview_mode() == PreviewMode.FACING_PAGES:
            notes.append("Click a visible page to jump to its source page.")
        if self._pdf and self.blank_check.isChecked() and self._composition and len(self._composition.items) % 2 == 1:
            notes.append("Full export will append an automatic final blank page.")
        return "\n".join(notes)

    def _active_item_description(self, item: OutputItem) -> str:
        if item.kind == OutputItemKind.SOURCE_PAGE and item.source_page_number is not None:
            return f"Source page {item.source_page_number}"
        if item.kind == OutputItemKind.INTENTIONAL_BLANK:
            placement = "before" if item.blank_placement == BlankPlacement.BEFORE else "after"
            return f"Intentional blank {placement} source page {item.blank_reference_source_page_number}"
        if item.kind == OutputItemKind.TEST_PADDING_BLANK:
            return "Test padding blank"
        if item.kind == OutputItemKind.AUTOMATIC_FINAL_BLANK:
            return "Automatic final blank"
        return "Output item"

    def refresh_preview(self, *_args) -> None:
        if not self._pdf:
            self.preview.set_state(None)
            self.current_item_label.setText("-")
            self.current_page_label.setText("-")
            self.output_position_label.setText("-")
            self.preview_location_label.setText("-")
            self.side_label.setText("-")
            self.shift_mode_label.setText("-")
            self.shift_value_label.setText("-")
            self.shift_direction_label.setText("-")
            self.scale_label.setText("-")
            self.content_margin_label.setText("Estimated margins: -")
            self._set_status("")
            self.blank_list.clear()
            return

        composition = self._compose_layout()
        if composition is None or not composition.items:
            self.preview.set_state(None)
            self.preview_location_label.setText("-")
            self._set_status("")
            return

        self._active_output_position = max(1, min(self._active_output_position, len(composition.items)))

        active_item = composition.item_at_output_position(self._active_output_position)
        mode = self._preview_mode()
        pages: list[PreviewPage] = []
        warnings: list[tuple[str | None, bool]] = []

        if mode == PreviewMode.SINGLE_PAGE:
            if active_item.kind == OutputItemKind.SOURCE_PAGE:
                page, warning = self._source_preview_page(active_item, compact=False)
            else:
                page = self._blank_preview_page(active_item)
                warning = (None, False)
            pages.append(page)
            page_label = self._active_item_description(active_item)
        else:
            spread = resolve_facing_spread(composition, self._active_output_position)
            if spread.left_item is not None:
                if spread.left_item.kind == OutputItemKind.SOURCE_PAGE:
                    left_page, left_warning = self._source_preview_page(spread.left_item, compact=True)
                else:
                    left_page = self._blank_preview_page(spread.left_item)
                    left_warning = (None, False)
                pages.append(left_page)
                warnings.append(left_warning)
            else:
                ref = spread.right_item
                if ref is not None:
                    pages.append(self._placeholder_preview_page(fitz.Rect(0, 0, ref.page_width_pt, ref.page_height_pt), "Blank / no facing page", "No source page on this side."))
                else:
                    pages.append(self._placeholder_preview_page(fitz.Rect(0, 0, 210, 297), "Blank / no facing page", "No source page on this side."))

            if spread.right_item is not None:
                if spread.right_item.kind == OutputItemKind.SOURCE_PAGE:
                    right_page, right_warning = self._source_preview_page(spread.right_item, compact=True)
                else:
                    right_page = self._blank_preview_page(spread.right_item)
                    right_warning = (None, False)
                pages.append(right_page)
                warnings.append(right_warning)
            else:
                ref = spread.left_item
                if ref is not None:
                    pages.append(self._placeholder_preview_page(fitz.Rect(0, 0, ref.page_width_pt, ref.page_height_pt), "Blank / no facing page", "No source page on this side."))
                else:
                    pages.append(self._placeholder_preview_page(fitz.Rect(0, 0, 210, 297), "Blank / no facing page", "No source page on this side."))
            page_label = f"Current spread: {format_facing_indicator(spread)}"

        if active_item.kind == OutputItemKind.SOURCE_PAGE and active_item.source_page_index is not None:
            page = self._pdf.document[active_item.source_page_index]
            shifts = self._selected_shifts()
            binding_side = self._selected_binding_side()
            placement = placement_for_page(page.rect, self.scale_spin.value(), shifts, active_item.side, binding_side)
            estimate = estimate_content_bounds(page)
            transformed = transformed_margins(page, estimate, self.scale_spin.value(), shifts, binding_side, active_item.side)
            crossing = transformed_content_crosses_edge(page, estimate, self.scale_spin.value(), shifts, binding_side, active_item.side)
            outer_warning = None
            warning_error = False
            if transformed:
                outer = min(transformed.left_mm, transformed.right_mm)
                if crossing:
                    outer_warning = "Visible content may be clipped on this page."
                    warning_error = True
                elif outer < 3.0:
                    outer_warning = "Possible clipping risk: estimated outer content margin is below 3 mm."
                    warning_error = True
                elif placement.outer_warning:
                    outer_warning = "The page canvas extends beyond the output edge. Check the preview for actual content clipping."
            warning_text = outer_warning
            if warning_text is None:
                for message, is_error in warnings:
                    if message:
                        warning_text = message
                        warning_error = is_error
                        break
            self.content_margin_label.setText(self._page_summary_text_from_estimate(active_item, estimate, transformed))
            shift_direction = "right" if page_shift_sign(active_item.side, self._selected_binding_side()) > 0 else "left"
            shift_value = format_mm(placement.shift_mm)
        else:
            warning_text = None
            warning_error = False
            for message, is_error in warnings:
                if message:
                    warning_text = message
                    warning_error = is_error
                    break
            self.content_margin_label.setText(self._active_item_description(active_item))
            shift_direction = "n/a"
            shift_value = "-"

        self.current_item_label.setText(f"Current item: {self._active_item_description(active_item)}")
        self.current_page_label.setText(page_label)
        self.output_position_label.setText(f"Output position: {self._active_output_position} of {len(composition.items)}")
        self.preview_location_label.setText(self._preview_footer_text(composition, active_item, mode))
        self.side_label.setText(f"Computed side: {active_item.side.label}")
        self.shift_mode_label.setText(f"Preview mode: {'Facing pages' if mode == PreviewMode.FACING_PAGES else 'Single page'}")
        self.shift_value_label.setText(
            f"Odd shift: {format_mm(self.odd_shift_spin.value())}, even shift: {format_mm(self.even_shift_spin.value())}, active shift: {shift_value}"
        )
        self.shift_direction_label.setText(f"Shift direction: {shift_direction}")
        self.scale_label.setText(f"Scale: {format_pct(self.scale_spin.value(), 1)}")
        self._set_status(warning_text or "", warning_error)

        state = PreviewState(
            mode=mode,
            page_count=len(composition.items),
            active_page_number=active_item.source_page_number or active_item.blank_reference_source_page_number or 1,
            indicator_text="",
            note_text="",
            scale=self.scale_spin.value(),
            binding_side=self._selected_binding_side(),
            show_original_position=self.show_original_check.isChecked(),
            show_binding_space=self.show_binding_space_check.isChecked(),
            pages=tuple(pages),
        )
        self.preview.set_state(state)

    def _page_summary_text_from_estimate(self, item: OutputItem, estimate, transformed) -> str:
        if item.kind != OutputItemKind.SOURCE_PAGE or estimate.margins is None:
            return self._active_item_description(item)
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

    def previous_page(self) -> None:
        if not self._composition:
            return
        self._set_active_output_position(previous_output_position(self._active_output_position, len(self._composition.items)))

    def next_page(self) -> None:
        if not self._composition:
            return
        self._set_active_output_position(next_output_position(self._active_output_position, len(self._composition.items)))

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
            items=selection.items,
        )
        self._export_test_selection_description = selection.description
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
        if not self._composition:
            return
        items = list(self._composition.items)
        if self.blank_check.isChecked() and len(items) % 2 == 1:
            last_item = items[-1]
            items.append(
                OutputItem(
                    kind=OutputItemKind.AUTOMATIC_FINAL_BLANK,
                    output_position=len(items) + 1,
                    side=DocumentLayout.side_for_output_position(len(items) + 1, self._first_page_side()),
                    page_width_pt=last_item.page_width_pt,
                    page_height_pt=last_item.page_height_pt,
                )
            )
        settings = ExportSettings(
            output_path=output_path,
            scale=self.scale_spin.value(),
            shift_settings=self._selected_shifts(),
            binding_side=self._selected_binding_side(),
            items=tuple(items),
        )
        self._start_export(settings, open_folder_after_success=False, test_export=False)

    def export_test_pdf(self) -> None:
        if not self._pdf:
            QtWidgets.QMessageBox.information(self, "Create Test PDF", "Open a PDF first.")
            return
        if not self._composition:
            return
        dialog = TestExportDialog(self.page_spin.value(), self._composition, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selection, warning = dialog.selection()
        if warning:
            self._set_status(warning, True)
        suggested_name = suggest_test_export_filename(self._pdf.path, selection, self._selected_shifts(), self.scale_spin.value())
        self._export_via_dialog(selection, suggested_name, dialog.open_folder_after_success())

    def _start_export(self, settings: ExportSettings, open_folder_after_success: bool, test_export: bool) -> None:
        if self._export_thread is not None:
            return
        self._export_open_folder_after_success = open_folder_after_success
        self._export_test_export = test_export
        self._export_result_handled = False
        self.export_button.setEnabled(False)
        self.test_export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._export_thread = QtCore.QThread()
        self._export_worker = ExportWorker(self._pdf, settings)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress_changed.connect(self._on_export_progress, QtCore.Qt.ConnectionType.QueuedConnection)
        self._export_worker.finished.connect(self._on_export_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._export_worker.failed.connect(self._on_export_failed, QtCore.Qt.ConnectionType.QueuedConnection)
        self._export_worker.cancelled.connect(self._on_export_cancelled, QtCore.Qt.ConnectionType.QueuedConnection)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_worker.cancelled.connect(self._export_thread.quit)
        self._export_worker.finished.connect(self._export_worker.deleteLater)
        self._export_worker.failed.connect(self._export_worker.deleteLater)
        self._export_worker.cancelled.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._on_export_thread_finished, QtCore.Qt.ConnectionType.QueuedConnection)
        self._export_thread.finished.connect(self._export_thread.deleteLater)
        self._export_thread.start()

    @QtCore.Slot(int, int)
    def _on_export_progress(self, current: int, total: int) -> None:
        self._assert_gui_thread()
        if self._export_result_handled:
            return
        self.statusBar().showMessage(f"Exporting page {current} of {total}")

    @QtCore.Slot()
    def _on_export_thread_finished(self) -> None:
        self._assert_gui_thread()
        self._export_worker = None
        self._export_thread = None
        self._export_open_folder_after_success = False
        self._export_test_export = False
        self._export_test_selection_description = ""
        self._export_result_handled = False

    def _restore_export_controls(self) -> None:
        self.export_button.setEnabled(True)
        self.test_export_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_status("")

    def _format_page_list(self, pages: tuple[int, ...]) -> str:
        if not pages:
            return "-"
        if len(pages) == 1:
            return str(pages[0])
        if list(pages) == list(range(pages[0], pages[-1] + 1)):
            return f"{pages[0]}-{pages[-1]}"
        return ", ".join(str(page) for page in pages)

    @QtCore.Slot(object)
    def _on_export_finished(self, result: object) -> None:
        self._assert_gui_thread()
        if self._export_result_handled:
            return
        self._export_result_handled = True
        self._current_output_path = getattr(result, "output_path", None)
        self._restore_export_controls()
        self.open_output_button.setEnabled(True)
        self.statusBar().showMessage("Export complete", 5000)
        intentional_blank_pages_added = getattr(result, "intentional_blank_pages_added", 0)
        automatic_final_blank_pages_added = getattr(result, "automatic_final_blank_pages_added", 0)
        test_padding_blank_pages_added = getattr(result, "test_padding_blank_pages_added", 0)
        total_output_pages = getattr(result, "pages_written", 0)
        if self._export_test_export:
            source_pages = self._format_page_list(tuple(getattr(result, "source_pages_exported", ())))
            selected_spread = self._export_test_selection_description or "-"
            message = (
                f"Output: {result.output_path}\n"
                f"Selected spread: {selected_spread}\n"
                f"Source pages included: {source_pages}\n"
                f"Intentional blanks included: {intentional_blank_pages_added}\n"
                f"Test-padding blanks added: {test_padding_blank_pages_added}\n"
                f"Total output pages: {total_output_pages}"
            )
        else:
            automatic_blank_text = "yes" if automatic_final_blank_pages_added else "no"
            message = (
                f"Output: {result.output_path}\n"
                f"Source pages written: {self._format_page_list(tuple(getattr(result, 'source_pages_exported', ())))}\n"
                f"Intentional blanks added: {intentional_blank_pages_added}\n"
                f"Automatic final blank added: {automatic_blank_text}\n"
                f"Total output pages: {total_output_pages}"
            )
        QtWidgets.QMessageBox.information(self, "Export complete", message)
        if self._export_open_folder_after_success and self._current_output_path is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._current_output_path.parent)))

    @QtCore.Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._assert_gui_thread()
        if self._export_result_handled:
            return
        self._export_result_handled = True
        self._current_output_path = None
        self._restore_export_controls()
        self.open_output_button.setEnabled(False)
        logging.exception("Export failed: %s", message)
        QtWidgets.QMessageBox.critical(self, "Export failed", message)

    @QtCore.Slot()
    def _on_export_cancelled(self) -> None:
        self._assert_gui_thread()
        if self._export_result_handled:
            return
        self._export_result_handled = True
        self._current_output_path = None
        self._restore_export_controls()
        self.open_output_button.setEnabled(False)
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
