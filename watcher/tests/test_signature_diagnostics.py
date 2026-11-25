from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from checkmate_watcher import signature_diagnostics as diagnostics


class FakeCanvas:
    def __init__(self) -> None:
        self.evaluated: list[str] = []

    async def evaluate(self, script, arg=None):
        self.evaluated.append("script")
        if script is diagnostics.CONTEXT_JS:
            return {
                "box": {"x": 10, "y": 20, "width": 300, "height": 150},
                "canvas": {"width": 300, "height": 150},
                "viewport": {"width": 1366, "height": 900},
                "devicePixelRatio": 1,
                "scroll": {"x": 0, "y": 0},
                "hit": {"tag": "CANVAS", "id": "", "className": ""},
                "covered": False,
                "inputLength": 0,
                "inputValue": "",
            }
        if script is diagnostics.READ_RECORDER_JS:
            return {
                "total": 145,
                "trusted": 145,
                "events": {"pointermove": 140},
            }
        if script is diagnostics.CANVAS_PNG_JS:
            payload = base64.b64encode(b"png").decode()
            return f"data:image/png;base64,{payload}"
        return True


class FakePage:
    def __init__(self) -> None:
        self.screenshots: list[Path] = []

    async def screenshot(self, path: str) -> None:
        target = Path(path)
        self.screenshots.append(target)
        target.write_bytes(b"page")


def test_decode_data_url_gere_les_valeurs_invalides():
    assert diagnostics.decode_data_url(None) == b""
    assert diagnostics.decode_data_url("pas-une-data-url") == b""
    assert diagnostics.decode_data_url("data:image/png;base64,cG5n") == b"png"


INK = {"count": 906, "minX": 54, "minY": 6, "maxX": 264, "maxY": 142}
ETAPE_RECOUVERTE = {
    "label": "premier essai",
    "ink": {"count": 0, "minX": 300, "minY": 150, "maxX": -1, "maxY": -1},
    "context": {
        "box": {"width": 302, "height": 152},
        "canvas": {"width": 300, "height": 150},
        "devicePixelRatio": 1.25,
        "covered": True,
        "hit": {"tag": "DIV", "className": "swal2-container"},
        "inputLength": 0,
    },
    "events": {"total": 145, "trusted": 0},
}


def capture(tmp_path, ink=INK):
    tracker = diagnostics.SignatureDiagnostics(tmp_path, FakePage())

    async def fill() -> None:
        canvas = FakeCanvas()
        await tracker.begin(canvas)
        await tracker.add_step("premier essai", canvas, ink)
        await tracker.save(canvas)

    asyncio.run(fill())
    return tracker


def test_une_capture_ecrit_diagnostic_canvas_et_page(tmp_path):
    tracker = capture(tmp_path)
    attempt = tracker.attempt_dir
    assert (attempt / "canvas.png").read_bytes() == b"png"
    assert (attempt / "page.png").read_bytes() == b"page"
    payload = json.loads(
        (attempt / "diagnostic.json").read_text(encoding="utf-8")
    )
    assert payload["steps"][0]["label"] == "avant le trace"
    assert payload["steps"][1]["ink"] == INK
    assert payload["steps"][1]["events"]["total"] == 145
    assert payload["steps"][1]["context"]["covered"] is False


def test_le_resume_contient_les_valeurs_utiles():
    resume = diagnostics.summary(ETAPE_RECOUVERTE)

    assert "canvas 302x152" in resume
    assert "dpr 1.25" in resume
    assert "recouvert True" in resume
    assert "swal2-container" in resume
    assert "evenements 145 dont 0 de confiance" in resume


def test_prune_garde_les_cinq_dernieres_tentatives(tmp_path):
    for index in range(7):
        attempt = tmp_path / f"signature-2026010{index}-000000"
        attempt.mkdir()
        (attempt / "diagnostic.json").write_text("{}", encoding="utf-8")

    diagnostics.prune(tmp_path)

    remaining = sorted(path.name for path in tmp_path.glob("signature-*"))
    assert len(remaining) == 5
    assert remaining[0] == "signature-20260102-000000"


def test_le_dossier_peut_etre_surcharge(monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKMATE_DIAGNOSTICS_DIR", str(tmp_path / "diag"))

    assert diagnostics.diagnostics_directory() == tmp_path / "diag"
