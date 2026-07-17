from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _run_app() -> int:
    try:
        from book_gutter.main_window import run_app
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").lower()
        message = str(exc).lower()
        if missing == "fitz" or "fitz" in message:
            print("PyMuPDF is missing.\nRun:\npython -m pip install -r requirements.txt")
            return 1
        if missing == "pyside6" or "pyside6" in message:
            print("PySide6 is missing.\nRun:\npython -m pip install -r requirements.txt")
            return 1
        if missing == "numpy" or "numpy" in message:
            print("NumPy is missing.\nRun:\npython -m pip install -r requirements.txt")
            return 1
        raise

    return run_app()


if __name__ == "__main__":
    raise SystemExit(_run_app())
