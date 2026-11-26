#!/usr/bin/env python3
"""Ecrit le marqueur du micro-resume utilise par les vieilles installations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTES = ROOT / "watcher/src/checkmate_watcher/release_notes.json"
MAX_TEASER = 240


def summary_marker(tag: str, notes_path: Path = DEFAULT_NOTES) -> str:
    version = tag.removeprefix("watcher-v")
    payload = json.loads(notes_path.read_text(encoding="utf-8"))
    note = payload.get(version, {}) if isinstance(payload, dict) else {}
    teaser = note.get("teaser", "0") if isinstance(note, dict) else "0"
    teaser = " ".join(str(teaser or "0").split())
    if len(teaser) > MAX_TEASER:
        raise ValueError(f"micro-resume trop long : {len(teaser)} caracteres")
    return f"CHECKMATE-SUMMARY: {teaser}"


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: release-summary.py <tag> [chemin du JSON]", file=sys.stderr)
        return 2
    tag = sys.argv[1]
    notes_path = Path(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_NOTES
    try:
        print(summary_marker(tag, notes_path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"micro-resume indisponible : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
