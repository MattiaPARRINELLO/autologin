"""Emplacements des fichiers, portables Linux, macOS et Windows."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "checkmate-watcher"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False))


def log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, appauthor=False))


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def default_env_path() -> Path:
    return config_dir() / "env"


def default_signature_path() -> Path:
    return config_dir() / "signature.json"


def default_profile_dir() -> Path:
    return data_dir() / "profile"


def default_state_file() -> Path:
    return data_dir() / "state.json"


def default_http_cookies_file() -> Path:
    return data_dir() / "http-cookies.json"


def default_log_file() -> Path:
    return log_dir() / "checkmate-watcher.log"


def default_update_dir() -> Path:
    return data_dir() / "updates"
