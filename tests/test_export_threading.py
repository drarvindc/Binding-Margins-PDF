import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PySide6 import QtCore, QtWidgets

from book_gutter.document_layout import DocumentLayout, OutputItem, OutputItemKind
from book_gutter.export_worker import ExportSettings
from book_gutter.main_window import MainWindow
from book_gutter.pdf_document import PdfDocument, PdfDocumentError
from book_gutter.page_side import PageSide
from book_gutter.pdf_transform import BindingSide, ShiftSettings


def make_pdf(path: Path, page_count: int = 3) -> None:
    doc = fitz.open()
    for index in range(page_count):
        page = doc.new_page(width=220, height=300)
        page.insert_text((40, 40), f"Page {index + 1}")
    doc.save(path)
    doc.close()


def make_items(page_count: int, include_final_blank: bool = False) -> tuple[OutputItem, ...]:
    composition = DocumentLayout().compose([(220.0, 300.0)] * page_count)
    items = list(composition.items)
    if include_final_blank:
        items.append(
            OutputItem(
                kind=OutputItemKind.AUTOMATIC_FINAL_BLANK,
                output_position=len(items) + 1,
                side=PageSide.RIGHT_ODD if len(items) % 2 == 0 else PageSide.LEFT_EVEN,
                page_width_pt=items[-1].page_width_pt,
                page_height_pt=items[-1].page_height_pt,
            )
        )
    return tuple(items)


def wait_for_export(window: MainWindow, qapp, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while window._export_thread is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert window._export_thread is None


def test_test_export_completion_runs_on_main_thread_and_restores_controls(tmp_path, qapp, monkeypatch):
    src = tmp_path / "source.pdf"
    out = tmp_path / "test_export.pdf"
    make_pdf(src, 3)

    window = MainWindow()
    window.load_pdf(src)

    threads: list[tuple[str, QtCore.QThread]] = []

    def fake_information(*args, **kwargs):
        threads.append(("information", QtCore.QThread.currentThread()))
        return QtWidgets.QMessageBox.StandardButton.Ok

    def fake_show_message(self, message, timeout=0):
        threads.append(("status", QtCore.QThread.currentThread()))

    monkeypatch.setattr(QtWidgets.QMessageBox, "information", fake_information)
    monkeypatch.setattr(QtWidgets.QStatusBar, "showMessage", fake_show_message)

    settings = ExportSettings(
        output_path=out,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(2),
    )
    window._start_export(settings, open_folder_after_success=False, test_export=True)
    wait_for_export(window, qapp)

    assert out.exists()
    assert window.export_button.isEnabled() is True
    assert window.test_export_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.open_output_button.isEnabled() is True
    assert all(thread == qapp.thread() for _, thread in threads)
    assert len([kind for kind, _thread in threads if kind == "information"]) == 1
    window.close()


def test_full_export_completion_runs_on_main_thread_and_restores_controls(tmp_path, qapp, monkeypatch):
    src = tmp_path / "source.pdf"
    out = tmp_path / "full_export.pdf"
    make_pdf(src, 3)

    window = MainWindow()
    window.load_pdf(src)

    threads: list[tuple[str, QtCore.QThread]] = []

    def fake_information(*args, **kwargs):
        threads.append(("information", QtCore.QThread.currentThread()))
        return QtWidgets.QMessageBox.StandardButton.Ok

    def fake_show_message(self, message, timeout=0):
        threads.append(("status", QtCore.QThread.currentThread()))

    monkeypatch.setattr(QtWidgets.QMessageBox, "information", fake_information)
    monkeypatch.setattr(QtWidgets.QStatusBar, "showMessage", fake_show_message)

    settings = ExportSettings(
        output_path=out,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(3, include_final_blank=True),
    )
    window._start_export(settings, open_folder_after_success=False, test_export=False)
    wait_for_export(window, qapp)

    exported = fitz.open(out)
    assert exported.page_count == 4
    exported.close()
    assert window.export_button.isEnabled() is True
    assert window.test_export_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.open_output_button.isEnabled() is True
    assert all(thread == qapp.thread() for _, thread in threads)
    assert len([kind for kind, _thread in threads if kind == "information"]) == 1
    window.close()


def test_export_failure_restores_controls_on_main_thread(tmp_path, qapp, monkeypatch):
    src = tmp_path / "source.pdf"
    out = tmp_path / "failed_export.pdf"
    make_pdf(src, 3)

    window = MainWindow()
    window.load_pdf(src)

    threads: list[QtCore.QThread] = []

    def fake_critical(*args, **kwargs):
        threads.append(QtCore.QThread.currentThread())
        return QtWidgets.QMessageBox.StandardButton.Ok

    def failing_export_items(self, *args, **kwargs):
        raise PdfDocumentError("boom")

    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", fake_critical)
    monkeypatch.setattr(PdfDocument, "export_items", failing_export_items)

    settings = ExportSettings(
        output_path=out,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(3),
    )
    window._start_export(settings, open_folder_after_success=False, test_export=False)
    wait_for_export(window, qapp)

    assert window.export_button.isEnabled() is True
    assert window.test_export_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.open_output_button.isEnabled() is False
    assert window._current_output_path is None
    assert threads == [qapp.thread()]
    window.close()


def test_export_cancellation_restores_controls_on_main_thread(tmp_path, qapp, monkeypatch):
    src = tmp_path / "source.pdf"
    out = tmp_path / "cancelled_export.pdf"
    make_pdf(src, 3)

    window = MainWindow()
    window.load_pdf(src)

    threads: list[QtCore.QThread] = []

    def fake_show_message(self, message, timeout=0):
        threads.append(QtCore.QThread.currentThread())

    def cancelled_export_items(self, *args, **kwargs):
        raise PdfDocumentError("Export cancelled.")

    monkeypatch.setattr(QtWidgets.QStatusBar, "showMessage", fake_show_message)
    monkeypatch.setattr(PdfDocument, "export_items", cancelled_export_items)

    settings = ExportSettings(
        output_path=out,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(3),
    )
    window._start_export(settings, open_folder_after_success=False, test_export=False)
    wait_for_export(window, qapp)

    assert window.export_button.isEnabled() is True
    assert window.test_export_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.open_output_button.isEnabled() is False
    assert window._current_output_path is None
    assert threads == [qapp.thread()]
    window.close()


def test_second_export_is_ignored_while_one_is_active(tmp_path, qapp, monkeypatch):
    src = tmp_path / "source.pdf"
    out1 = tmp_path / "first.pdf"
    out2 = tmp_path / "second.pdf"
    make_pdf(src, 3)

    window = MainWindow()
    window.load_pdf(src)

    started = threading.Event()
    release = threading.Event()
    original_export_items = PdfDocument.export_items

    def blocking_export_items(self, *args, **kwargs):
        started.set()
        assert release.wait(5.0)
        return original_export_items(self, *args, **kwargs)

    monkeypatch.setattr(PdfDocument, "export_items", blocking_export_items)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Ok)

    first_settings = ExportSettings(
        output_path=out1,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(3),
    )
    second_settings = ExportSettings(
        output_path=out2,
        scale=100.0,
        shift_settings=ShiftSettings(5.0, 5.0),
        binding_side=BindingSide.LEFT,
        items=make_items(3),
    )
    window._start_export(first_settings, open_folder_after_success=False, test_export=False)
    assert started.wait(5.0) is True
    first_thread = window._export_thread
    first_worker = window._export_worker

    window._start_export(second_settings, open_folder_after_success=False, test_export=False)
    assert window._export_thread is first_thread
    assert window._export_worker is first_worker

    release.set()
    wait_for_export(window, qapp)
    assert out1.exists()
    assert not out2.exists()
    window.close()
