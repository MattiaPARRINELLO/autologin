"""Configuration du logging, avec fichier tournant pour Windows et Linux."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import default_log_file

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATEFMT = "%H:%M:%S"
MAX_BYTES = 2_000_000
BACKUP_COUNT = 5


def _utf8_stream(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    return stream


def setup_logging(verbose: bool = False, log_file: Path | None = None) -> Path:
    """Configure stdout + fichier tournant et renvoie le chemin du fichier."""
    target = log_file or default_log_file()
    target.parent.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    if sys.stdout is not None:
        stream = logging.StreamHandler(_utf8_stream(sys.stdout))
        stream.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT))
        root.addHandler(stream)

    file_handler = RotatingFileHandler(
        target,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT))
    root.addHandler(file_handler)
    return target
