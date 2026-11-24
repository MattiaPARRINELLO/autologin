"""Trace detaillee d'une tentative de signature.

Chaque tentative ecrit un dossier dans ``diagnostics/`` : geometrie du canvas,
element qui le recouvre, compteurs d'evenements recus, encre mesuree, valeur du
champ cache du site, capture du canvas et capture de la page. Le
``support-bundle`` embarque ces dossiers pour diagnostiquer un cas reel.

Tout est best-effort : une erreur de diagnostic ne doit jamais empecher de
signer.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from . import paths

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def diagnostics_directory() -> Path:
    """Dossier des traces de signature, surchargeable pour les tests."""
    override = os.environ.get("CHECKMATE_DIAGNOSTICS_DIR")
    if override:
        return Path(override).expanduser()
    return paths.data_dir() / "diagnostics"


INSTALL_RECORDER_JS = """
(canvas) => {
  const state = { events: {}, total: 0, trusted: 0, first: null, last: null };
  window.__checkmateSignature = state;
  const kinds = [
    'pointerdown', 'pointermove', 'pointerup',
    'mousedown', 'mousemove', 'mouseup'
  ];
  for (const kind of kinds) {
    state.events[kind] = 0;
    canvas.addEventListener(kind, (event) => {
      state.events[kind] += 1;
      state.total += 1;
      if (event.isTrusted) state.trusted += 1;
      const point = {
        kind,
        x: Math.round(event.clientX),
        y: Math.round(event.clientY),
        buttons: event.buttons,
        trusted: event.isTrusted
      };
      if (!state.first) state.first = point;
      state.last = point;
    }, true);
  }
  return true;
}
"""

READ_RECORDER_JS = "() => window.__checkmateSignature || null"

CONTEXT_JS = """
(canvas) => {
  const rect = canvas.getBoundingClientRect();
  const hit = document.elementFromPoint(
    rect.left + rect.width / 2,
    rect.top + rect.height / 2
  );
  const describe = (el) => el ? {
    tag: el.tagName,
    id: el.id,
    className: String(el.className).slice(0, 120)
  } : null;
  const input = document.querySelector(
    "input[data-written-signature-target='input']"
  );
  const value = input ? String(input.value) : '';
  return {
    box: {
      x: Math.round(rect.left),
      y: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    },
    canvas: { width: canvas.width, height: canvas.height },
    viewport: { width: window.innerWidth, height: window.innerHeight },
    devicePixelRatio: window.devicePixelRatio,
    scroll: { x: Math.round(window.scrollX), y: Math.round(window.scrollY) },
    hit: describe(hit),
    covered: !(hit === canvas || canvas.contains(hit)),
    inputLength: value.length,
    inputValue: value.slice(0, 400)
  };
}
"""

CANVAS_PNG_JS = "(canvas) => canvas.toDataURL('image/png')"


class SignatureDiagnostics:
    def __init__(self, directory: Path, page) -> None:
        self.directory = directory
        self.page = page
        self.payload: dict = {"steps": []}
        self.attempt_dir = directory / datetime.now().strftime(
            "signature-%Y%m%d-%H%M%S-%f"
        )

    async def begin(self, canvas) -> None:
        try:
            await canvas.evaluate(INSTALL_RECORDER_JS)
        except Exception:
            logger.debug("enregistreur d'evenements indisponible", exc_info=True)
        await self.add_step("avant le trace", canvas, None)

    async def add_step(self, label: str, canvas, ink: dict | None) -> None:
        try:
            context = await canvas.evaluate(CONTEXT_JS)
            events = await canvas.evaluate(READ_RECORDER_JS)
        except Exception:
            logger.debug("etape de diagnostic indisponible", exc_info=True)
            return
        step = {"label": label, "ink": ink, "context": context, "events": events}
        self.payload["steps"].append(step)
        logger.info("diagnostic signature (%s) : %s", label, summary(step))

    async def save(self, canvas) -> None:
        try:
            self.attempt_dir.mkdir(parents=True, exist_ok=True)
            data_url = await canvas.evaluate(CANVAS_PNG_JS)
            (self.attempt_dir / "canvas.png").write_bytes(decode_data_url(data_url))
            if self.page is not None:
                await self.page.screenshot(path=str(self.attempt_dir / "page.png"))
            self.payload["savedAt"] = datetime.now().isoformat(timespec="seconds")
            (self.attempt_dir / "diagnostic.json").write_text(
                json.dumps(self.payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("diagnostic de signature non enregistre", exc_info=True)
            return
        prune(self.directory)
        logger.info("diagnostic signature enregistre : %s", self.attempt_dir)


def decode_data_url(data_url: str | None) -> bytes:
    if not data_url or "," not in data_url:
        return b""
    return base64.b64decode(data_url.split(",", 1)[1])


def _ink_text(ink: dict) -> str:
    if not ink:
        return "encre non mesuree"
    return (
        f"encre {ink.get('count')}"
        f" [{ink.get('minX')},{ink.get('minY')}-{ink.get('maxX')},{ink.get('maxY')}]"
    )


def _canvas_text(context: dict, box: dict) -> str:
    canvas = context.get("canvas", {})
    return (
        f"canvas {box.get('width')}x{box.get('height')}"
        f" ({canvas.get('width')}x{canvas.get('height')} px),"
        f" dpr {context.get('devicePixelRatio')},"
    )


def _details_text(context: dict, events: dict, hit: dict, ink_text: str) -> str:
    return (
        f" recouvert {context.get('covered')}"
        f" par {hit.get('tag')}.{hit.get('className')},"
        f" evenements {events.get('total')}"
        f" dont {events.get('trusted')} de confiance,"
        f" {ink_text},"
        f" champ site {context.get('inputLength')} caracteres"
    )


def summary(step: dict) -> str:
    context = step.get("context") or {}
    events = step.get("events") or {}
    hit = context.get("hit") or {}
    box = context.get("box") or {}
    ink_text = _ink_text(step.get("ink") or {})
    return _canvas_text(context, box) + _details_text(context, events, hit, ink_text)


def prune(directory: Path, keep: int = MAX_ATTEMPTS) -> None:
    attempts = sorted(
        (path for path in directory.glob("signature-*") if path.is_dir()),
        reverse=True,
    )
    for stale in attempts[keep:]:
        for file in stale.glob("*"):
            file.unlink(missing_ok=True)
        stale.rmdir()
