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


def _ensure_log_dir(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)


def _reset_root_logger(level: int) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    return root


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, LOG_DATEFMT)


def _add_stdout_handler(root: logging.Logger) -> None:
    if sys.stdout is None:
        return
    stream = logging.StreamHandler(_utf8_stream(sys.stdout))
    stream.setFormatter(_make_formatter())
    root.addHandler(stream)


def _add_file_handler(root: logging.Logger, target: Path) -> None:
    handler = RotatingFileHandler(
        target,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(_make_formatter())
    root.addHandler(handler)


def setup_logging(verbose: bool = False, log_file: Path | None = None) -> Path:
    """Configure stdout + fichier tournant et renvoie le chemin du fichier."""
    target = log_file or default_log_file()
    _ensure_log_dir(target)

    level = logging.DEBUG if verbose else logging.INFO
    root = _reset_root_logger(level)
    _add_stdout_handler(root)
    _add_file_handler(root, target)
    return target
