from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from checkmate_watcher import paths
from checkmate_watcher.logging_setup import setup_logging


@contextmanager
def root_restaure(root: logging.Logger) -> Iterator[None]:
    previous = list(root.handlers), root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            handler.close()
        root.handlers[:] = previous[0]
        root.setLevel(previous[1])


def flush_handlers(root: logging.Logger) -> None:
    for handler in root.handlers:
        handler.flush()


def test_les_dossiers_portent_le_nom_de_l_application():
    assert paths.config_dir().name == "checkmate-watcher"
    assert paths.data_dir().name == "checkmate-watcher"
    assert "checkmate-watcher" in paths.log_dir().parts


def test_logging_ecrit_dans_le_fichier(tmp_path):
    target = tmp_path / "logs" / "checkmate.log"
    root = logging.getLogger()
    with root_restaure(root):
        assert setup_logging(log_file=target) == target
        logging.getLogger("test").info("bonjour")
        flush_handlers(root)
        assert "bonjour" in target.read_text(encoding="utf-8")
