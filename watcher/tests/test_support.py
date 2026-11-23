from __future__ import annotations

import zipfile
from dataclasses import replace

from checkmate_watcher import paths
from checkmate_watcher.config import default_config
from checkmate_watcher.support import build_support_bundle


def test_archive_sans_secret(tmp_path, monkeypatch):
    config = default_config()
    config = replace(
        config,
        cesar=replace(config.cesar, username="eleve", password="secret-du-compte"),
        signature=replace(config.signature, file=tmp_path / "signature.json"),
    )
    log_file = tmp_path / "checkmate.log"
    log_file.write_text(
        "demarrage\npassword=secret-du-compte\nsurveillance active\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "default_log_file", lambda: log_file)

    bundle = build_support_bundle(
        config,
        tmp_path / "config.toml",
        tmp_path / "bundle.zip",
    )
    assert bundle.is_file()

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        content = "\n".join(
            archive.read(name).decode("utf-8", errors="replace") for name in names
        )

    assert "diagnostic.txt" in names
    assert "config-sans-secrets.toml" in names
    assert "logs.txt" in names
    assert "secret-du-compte" not in content
    assert "ligne masquee" in content
    assert "version:" in content


def test_archive_contient_les_diagnostics(tmp_path):
    config = default_config()
    diagnostics = tmp_path / "diagnostics" / "signature-20260101-000000"
    diagnostics.mkdir(parents=True)
    (diagnostics / "diagnostic.json").write_text("{}", encoding="utf-8")
    (diagnostics / "canvas.png").write_bytes(b"png")

    bundle = build_support_bundle(
        config,
        tmp_path / "config.toml",
        tmp_path / "bundle.zip",
        diagnostics_dir=tmp_path / "diagnostics",
    )

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
    assert "diagnostics/signature-20260101-000000/diagnostic.json" in names
    assert "diagnostics/signature-20260101-000000/canvas.png" in names
