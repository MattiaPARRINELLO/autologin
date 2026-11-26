from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release-summary.py"


def run_script(tag: str, notes: Path | None = None) -> str:
    command = [sys.executable, str(SCRIPT), tag]
    if notes is not None:
        command.append(str(notes))
    result = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=5
    )
    return result.stdout.strip()


def test_resume_de_la_release_stable():
    marker = run_script("watcher-v0.7.0")
    assert marker.startswith("CHECKMATE-SUMMARY: ")
    assert "2,3×" in marker


def test_beta_sans_micro_resume():
    assert run_script("watcher-v0.7.0-beta.5") == "CHECKMATE-SUMMARY: 0"


def test_version_sans_resume():
    assert run_script("watcher-v9.9.9") == "CHECKMATE-SUMMARY: 0"


def test_micro_resume_sur_une_seule_ligne(tmp_path):
    notes = tmp_path / "notes.json"
    notes.write_text(
        json.dumps({"1.0.0": {"teaser": "Une ligne\npuis une autre"}}),
        encoding="utf-8",
    )
    assert run_script("watcher-v1.0.0", notes) == (
        "CHECKMATE-SUMMARY: Une ligne puis une autre"
    )
