"""Paquet de support sans secrets."""

from __future__ import annotations

import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import tomli_w

from . import BUILD, __version__, paths
from .autostart import autostart_enabled
from .config import Config, config_to_dict
from .credentials import keyring_available
from .signature import SignatureError, load_signature

MAX_LOG_LINES = 400
MAX_DIAGNOSTIC_BYTES = 5_000_000


def _contains_secret(line: str) -> bool:
    lowered = line.lower()
    markers = ("password", "passwd", "mot de passe")
    return any(marker in lowered for marker in markers)


def _redact_line(line: str) -> str:
    if _contains_secret(line):
        return "[ligne masquee]"
    return line


def _redact(text: str) -> str:
    return "\n".join(_redact_line(line) for line in text.splitlines())


def _log_tail(log_file: Path) -> str:
    if not log_file.is_file():
        return f"[aucun log dans {log_file}]"
    try:
        lines = log_file.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError as exc:
        return f"[lecture des logs impossible : {exc}]"
    return _redact("\n".join(lines[-MAX_LOG_LINES:]))


def _signature_summary(config: Config) -> str:
    try:
        points = load_signature(config.signature.file)
        return f"{len(points)} points"
    except SignatureError as exc:
        return f"indisponible ({exc})"


def _header_lines(config_path: Path) -> list[str]:
    return [
        f"version: {__version__} (build {BUILD})",
        f"os: {platform.platform()}",
        f"python: {sys.version.split()[0]}",
        f"config: {config_path}",
    ]


def _status_lines(config: Config, signature: str) -> list[str]:
    return [
        f"mot de passe: {'present' if config.cesar.password else 'absent'}",
        f"signature: {signature}",
        f"trousseau: {keyring_available()}",
        f"demarrage auto: {autostart_enabled()}",
        f"profil: {config.watcher.profile_dir}",
        f"logs: {paths.default_log_file()}",
        f"diagnostics: {paths.data_dir() / 'diagnostics'}",
    ]


def diagnostics(config: Config, config_path: Path) -> str:
    lines = _header_lines(config_path)
    return "\n".join(lines + _status_lines(config, _signature_summary(config)))


def _add_diagnostics(archive: zipfile.ZipFile, directory: Path) -> None:
    """Ajoute les dernieres traces de signature, dans la limite de taille."""
    if directory.is_dir():
        _write_diagnostics(archive, directory)


def _write_diagnostics(archive: zipfile.ZipFile, directory: Path) -> None:
    total = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        if total + size > MAX_DIAGNOSTIC_BYTES:
            break
        archive.write(path, f"diagnostics/{path.relative_to(directory)}")
        total += size


class Texts(NamedTuple):
    config: str
    log: str
    summary: str


def _resolve_target(output: Path | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default = paths.data_dir() / "support" / f"checkmate-support-{stamp}.zip"
    target = Path(output or default).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _bundle_texts(config: Config, config_path: Path) -> Texts:
    config_text = tomli_w.dumps(config_to_dict(config))
    log_text = _log_tail(paths.default_log_file())
    return Texts(config_text, log_text, diagnostics(config, config_path))


def _write_archive(
    target: Path, texts: Texts, diagnostics_dir: Path | None
) -> None:
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("diagnostic.txt", texts.summary + "\n")
        archive.writestr("config-sans-secrets.toml", texts.config)
        archive.writestr("logs.txt", texts.log + "\n")
        folder = diagnostics_dir or (paths.data_dir() / "diagnostics")
        _add_diagnostics(archive, folder)


def build_support_bundle(
    config: Config,
    config_path: Path,
    output: Path | None = None,
    diagnostics_dir: Path | None = None,
) -> Path:
    """Cree une archive de diagnostic sans mot de passe ni signature."""
    target = _resolve_target(output)
    texts = _bundle_texts(config, config_path)
    _write_archive(target, texts, diagnostics_dir)
    return target
