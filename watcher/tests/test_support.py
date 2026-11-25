from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

from checkmate_watcher import paths
from checkmate_watcher.config import Config, default_config
from checkmate_watcher.support import build_support_bundle


def _config_avec_compte(config: Config, tmp_path: Path) -> Config:
    cesar = replace(
        config.cesar, username="eleve", password="secret-du-compte"
    )
    signature = replace(config.signature, file=tmp_path / "signature.json")
    return replace(config, cesar=cesar, signature=signature)


def _ecrire_log_avec_secret(tmp_path: Path, monkeypatch) -> Path:
    log_file = tmp_path / "checkmate.log"
    contenu = "demarrage\npassword=secret-du-compte\nsurveillance active\n"
    log_file.write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(paths, "default_log_file", lambda: log_file)
    return log_file


def _construire_bundle(
    config: Config, tmp_path: Path, diagnostics_dir: Path | None = None
) -> Path:
    return build_support_bundle(
        config,
        tmp_path / "config.toml",
        tmp_path / "bundle.zip",
        diagnostics_dir=diagnostics_dir,
    )


def _lire_archive(bundle: Path) -> tuple[list[str], str]:
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        content = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in names
        )
    return names, content


def _verifier_archive(names: list[str], content: str) -> None:
    assert "diagnostic.txt" in names
    assert "config-sans-secrets.toml" in names
    assert "logs.txt" in names
    assert "secret-du-compte" not in content
    assert "ligne masquee" in content
    assert "version:" in content


def _creer_diagnostics(tmp_path: Path) -> Path:
    diagnostics = tmp_path / "diagnostics" / "signature-20260101-000000"
    diagnostics.mkdir(parents=True)
    (diagnostics / "diagnostic.json").write_text("{}", encoding="utf-8")
    (diagnostics / "canvas.png").write_bytes(b"png")
    return tmp_path / "diagnostics"


def test_archive_sans_secret(tmp_path, monkeypatch):
    config = _config_avec_compte(default_config(), tmp_path)
    _ecrire_log_avec_secret(tmp_path, monkeypatch)
    bundle = _construire_bundle(config, tmp_path)
    names, content = _lire_archive(bundle)
    _verifier_archive(names, content)


def test_archive_contient_les_diagnostics(tmp_path):
    config = default_config()
    diagnostics = _creer_diagnostics(tmp_path)
    names, _ = _lire_archive(_construire_bundle(config, tmp_path, diagnostics))
    assert "diagnostics/signature-20260101-000000/diagnostic.json" in names
    assert "diagnostics/signature-20260101-000000/canvas.png" in names
