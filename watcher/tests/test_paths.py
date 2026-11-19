from __future__ import annotations

import logging

from checkmate_watcher import paths
from checkmate_watcher.logging_setup import setup_logging


def test_chemins_par_defaut_coherents():
    assert paths.default_config_path() == paths.config_dir() / "config.toml"
    assert paths.default_env_path() == paths.config_dir() / "env"
    assert paths.default_signature_path() == paths.config_dir() / "signature.json"
    assert paths.default_profile_dir() == paths.data_dir() / "profile"
    assert paths.default_state_file() == paths.data_dir() / "state.json"
    assert paths.default_log_file() == paths.log_dir() / "checkmate-watcher.log"


def test_les_dossiers_portent_le_nom_de_l_application():
    assert paths.config_dir().name == "checkmate-watcher"
    assert paths.data_dir().name == "checkmate-watcher"
    assert "checkmate-watcher" in paths.log_dir().parts


def test_logging_ecrit_dans_le_fichier(tmp_path):
    target = tmp_path / "logs" / "checkmate.log"
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level

    try:
        written = setup_logging(log_file=target)
        assert written == target
        logging.getLogger("test").info("bonjour")
        for handler in root.handlers:
            handler.flush()
        assert "bonjour" in target.read_text(encoding="utf-8")
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)
