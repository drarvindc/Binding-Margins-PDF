from __future__ import annotations

import logging
from pathlib import Path


def configure_logging() -> Path:
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "book_gutter_pdf.log"
    if not logging.getLogger().handlers:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    return log_file
