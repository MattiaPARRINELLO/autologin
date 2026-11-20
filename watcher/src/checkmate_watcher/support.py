"""Paquet de support sans secrets."""

from __future__ import annotations

import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import tomli_w

from . import __version__, paths
from .autostart import autostart_enabled
from .config import Config, config_to_dict
from .credentials import keyring_available
from .signature import SignatureError, load_signature

MAX_LOG_LINES = 400


def _redact(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if "password" in lowered or "passwd" in lowered or "mot de passe" in lowered:
            lines.append("[ligne masquee]")
        else:
            lines.append(line)
    return "\n".join(lines)


def _log_tail(log_file: Path) -> str:
    if not log_file.is_file():
        return f"[aucun log dans {log_file}]"
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"[lecture des logs impossible : {exc}]"
    return _redact("\n".join(lines[-MAX_LOG_LINES:]))


def diagnostics(config: Config, config_path: Path) -> str:
    try:
        points = load_signature(config.signature.file)
        signature = f"{len(points)} points"
    except SignatureError as exc:
        signature = f"indisponible ({exc})"

    return "\n".join(
        [
            f"version: {__version__}",
            f"os: {platform.platform()}",
            f"python: {sys.version.split()[0]}",
            f"config: {config_path}",
            f"mot de passe: {'present' if config.cesar.password else 'absent'}",
            f"signature: {signature}",
            f"trousseau: {keyring_available()}",
            f"demarrage auto: {autostart_enabled()}",
            f"profil: {config.watcher.profile_dir}",
            f"logs: {paths.default_log_file()}",
        ]
    )


def build_support_bundle(
    config: Config,
    config_path: Path,
    output: Path | None = None,
) -> Path:
    """Cree une archive de diagnostic sans mot de passe ni signature."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output or (paths.data_dir() / "support" / f"checkmate-support-{stamp}.zip")
    target = Path(target).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    config_text = tomli_w.dumps(config_to_dict(config))
    log_text = _log_tail(paths.default_log_file())
    summary = diagnostics(config, config_path)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostic.txt", summary + "\n")
        archive.writestr("config-sans-secrets.toml", config_text)
        archive.writestr("logs.txt", log_text + "\n")

    return target
