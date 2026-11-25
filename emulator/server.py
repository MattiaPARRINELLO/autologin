#!/usr/bin/env python3
"""Emulateur local de CESAR Emineo.

Serveur autonome, sans dependance, qui imite le parcours reel :
connexion, tableau de bord, bouton d'emargement, canvas de signature,
confirmation et etat persistant en memoire.

Lancer :
    python3 emulator/server.py --port 8765

Ou servir un scenario capture a la place des pages generees :
    python3 emulator/server.py --port 8765 --scenario emulator/scenarios/demo

Puis configurer le watcher avec base_url = "http://127.0.0.1:8765".
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scenario import Scenario, ScenarioError, load_scenario

COOKIE_NAME = "cesar_session"
SLOW_ANIMATION = "slow-animation"
MOUSE_EVENTS_ONLY = "mouse-events-only"
VARIANT_CHOICES = (SLOW_ANIMATION, MOUSE_EVENTS_ONLY)


@dataclass
class AttendanceState:
    open: bool = False
    signed: bool = False
    session_id: int = 0
    signature_points: int = 0
    signed_at: str | None = None
    opened_at: str | None = None


class Emulator:
    def __init__(self, username, password, token, run_id, **options) -> None:
        self.username = username
        self.password = password
        self.token = token
        self.run_id = run_id
        delay = options.get("attendance_close_delay_ms", 0)
        self.attendance_close_delay_ms = max(0, delay)
        self.variants = frozenset(options.get("variants", frozenset()))
        self._init_state()

    def _init_state(self) -> None:
        self.lock = threading.Lock()
        self.state = AttendanceState()

    def _reset_attendance_state(self) -> None:
        self.state.open = True
        self.state.signed = False
        self.state.signature_points = 0
        self.state.signed_at = None

    def open_attendance(self) -> AttendanceState:
        with self.lock:
            if not self.state.open:
                self.state.session_id += 1
                self.state.opened_at = datetime.now().isoformat(timespec="seconds")
            self._reset_attendance_state()
            return self.state

    def close_attendance(self) -> AttendanceState:
        with self.lock:
            self.state.open = False
            return self.state

    def reset(self) -> AttendanceState:
        with self.lock:
            self.state = AttendanceState()
            return self.state

    def sign(self, points: list) -> tuple[bool, str]:
        with self.lock:
            error = self._sign_error(points)
            if error is not None:
                return False, error
            self._apply_signature(points)
            return True, "Votre presence a bien ete prise en compte."

    def _sign_error(self, points: list) -> str | None:
        if not points:
            return "Signature vide."
        if not self.state.open:
            return "Aucun emargement n'est ouvert."
        if self.state.signed:
            return "Votre presence est deja enregistree."
        return None

    def _apply_signature(self, points: list) -> None:
        self.state.signed = True
        self.state.signature_points = len(points)
        self.state.signed_at = datetime.now().isoformat(timespec="seconds")

    def as_dict(self) -> dict:
        with self.lock:
            return {
                "attendance_open": self.state.open,
                "signed": self.state.signed,
                "session_id": self.state.session_id,
                "signature_points": self.state.signature_points,
                "signed_at": self.state.signed_at,
                "opened_at": self.state.opened_at,
            }


EMULATOR: Emulator | None = None
SCENARIO: Scenario | None = None


def scenario_state() -> str:
    assert EMULATOR is not None
    if EMULATOR.state.signed:
        return "signed"
    if EMULATOR.state.open:
        return "open"
    return "default"


def scenario_page(path: str) -> bytes | None:
    if SCENARIO is None:
        return None
    return SCENARIO.page_html(path, scenario_state())


def scenario_asset(path: str) -> tuple[bytes, str] | None:
    if SCENARIO is None:
        return None
    return SCENARIO.asset(path)


PAGE_STYLE = """
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a;
  color: #e2e8f0; }
  header { display: flex; justify-content: space-between; align-items: center;
           padding: 16px 28px; background: #1e293b; border-bottom: 1px solid
           #334155; }
  header h1 { font-size: 18px; margin: 0; letter-spacing: .3px; }
  header nav a { color: #94a3b8; text-decoration: none; margin-left: 18px;
  font-size: 14px; }
  header nav a:hover { color: #e2e8f0; }
  main { max-width: 980px; margin: 0 auto; padding: 32px 24px 64px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px;
  padding: 24px; }
  .muted { color: #94a3b8; font-size: 14px; }
  button { font: inherit; border: 0; border-radius: 10px; padding: 12px 20px;
  cursor: pointer; font-weight: 700; }
  .primary { background: #38bdf8; color: #082f49; }
  .success { background: #22c55e; color: #052e16; }
  .danger { background: #ef4444; color: #450a0a; }
  .ghost { background: #334155; color: #e2e8f0; }
  .calendar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;
  margin-top: 18px; }
  .slot { background: #0f172a; border: 1px solid #334155; border-radius: 10px;
          padding: 14px 10px; font-size: 13px; color: #94a3b8; min-height:
          74px; }
  .slot strong { display: block; color: #e2e8f0; font-size: 14px;
  margin-bottom: 4px; }
  .status { display: inline-block; padding: 6px 12px; border-radius: 999px;
  font-size: 13px; font-weight: 700; }
  .status.open { background: #14532d; color: #bbf7d0; }
  .status.closed { background: #334155; color: #cbd5e1; }
  #modal { position: fixed; inset: 0; background: rgba(2, 6, 23, .75);
           display: none; align-items: center; justify-content: center;
           padding: 20px; }
  #modal.visible { display: flex; }
  .dialog { background: #1e293b; border: 1px solid #334155; border-radius:
  18px;
            padding: 24px; width: 380px; box-shadow: 0 30px 80px
            rgba(0,0,0,.5); }
  canvas { background: #fff; border-radius: 12px; display: block; width: 100%;
  cursor: crosshair; touch-action: none; }
  .swal2-html-container { margin-top: 16px; color: #86efac; font-weight: 600; }
"""

MODAL_ANIMATION_STYLE = """
  @keyframes modal-in {
    from { opacity: 0; transform: translateY(-32px) scale(.92); }
    to { opacity: 1; transform: none; }
  }
  #modal.visible .dialog { animation: modal-in 1.2s ease-out; }
"""

DASHBOARD_SCRIPT = """
  const modal = document.getElementById('modal');
  const canvas = document.getElementById('pad');
  const save = document.getElementById('save');
  const swal = document.querySelector('.swal2-html-container');
  const points = [];
  let drawing = false;

  function position(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height)
    };
  }

  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#0f172a';

    __CANVAS_WIRING__
  }

  const trigger = document.querySelector('.buttonPresent');
  if (trigger) {
    trigger.addEventListener('click', () => modal.classList.add('visible'));
  }

  if (save) {
    save.addEventListener('click', async () => {
      const response = await fetch('/api/signature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points })
      });
      const data = await response.json();
      swal.textContent = data.message;
      save.disabled = true;
      window.setTimeout(() => {
        if (trigger) trigger.remove();
        if (canvas) canvas.remove();
      }, __ATTENDANCE_CLOSE_DELAY_MS__);
    });
  }
"""

CANVAS_WIRING = {
    "pointer": """
    canvas.addEventListener('pointerdown', (event) => {
      drawing = true;
      canvas.setPointerCapture(event.pointerId);
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'start' });
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    });

    canvas.addEventListener('pointermove', (event) => {
      if (!drawing) return;
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'move' });
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    });

    function endStroke(event) {
      if (!drawing) return;
      drawing = false;
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'end' });
      ctx.stroke();
    }
    canvas.addEventListener('pointerup', endStroke);
    canvas.addEventListener('pointercancel', endStroke);
""",
    "mouse": """
    canvas.addEventListener('mousedown', (event) => {
      drawing = true;
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'start' });
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    });

    canvas.addEventListener('mousemove', (event) => {
      if (!drawing) return;
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'move' });
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    });

    function endStroke(event) {
      if (!drawing) return;
      drawing = false;
      const p = position(event);
      points.push({ x: p.x, y: p.y, type: 'end' });
      ctx.stroke();
    }
    canvas.addEventListener('mouseup', endStroke);
    canvas.addEventListener('mouseleave', endStroke);
""",
}


def canvas_wiring(variants: frozenset[str]) -> str:
    if MOUSE_EVENTS_ONLY in variants:
        return CANVAS_WIRING["mouse"]
    return CANVAS_WIRING["pointer"]


PAGE_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{page_style}</style>
{extra_style}
</head>
<body>
{body}
<script>{script}</script>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<main style="max-width:420px;margin-top:12vh">
  <div class="card">
    <h1 style="margin-top:0">CESAR Emineo</h1>
    <p class="muted">Emulateur local. Identifiants par defaut : demo /
    demo.</p>
    {error_block}
    <form method="post" action="/connexion">
      <label class="muted" for="username">Identifiant</label>
      <input id="username" name="username" autocomplete="username"
             style="width:100%;padding:12px;margin:6px 0
             16px;border-radius:10px;border:1px solid
             #334155;background:#0f172a;color:#e2e8f0">
      <label class="muted" for="password">Mot de passe</label>
      <input id="password" name="password" type="password"
      autocomplete="current-password"
             style="width:100%;padding:12px;margin:6px 0
             20px;border-radius:10px;border:1px solid
             #334155;background:#0f172a;color:#e2e8f0">
      <button class="btn-primary primary" type="submit" style="width:100%">Se
      connecter</button>
    </form>
  </div>
</main>
"""


def _page_values(title: str, body: str, script: str, style: str) -> dict:
    extra_style = f"<style>{style}</style>" if style else ""
    return {
        "title": title,
        "page_style": PAGE_STYLE,
        "extra_style": extra_style,
        "body": body,
        "script": script,
    }


def render_page(title: str, body: str, *, script: str = "", style: str = "") -> bytes:
    html = PAGE_TEMPLATE.format(**_page_values(title, body, script, style))
    return html.encode("utf-8")


def render_login(error: bool = False) -> bytes:
    error_block = (
        '<p style="color:#fca5a5;font-weight:700">Identifiants incorrects.</p>'
        if error
        else ""
    )
    body = LOGIN_TEMPLATE.format(error_block=error_block)
    return render_page("CESAR - connexion", body)


OPEN_MODAL = """
<div id="modal">
  <div class="dialog">
    <h2 style="margin-top:0">Signature de presence</h2>
    <p class="muted">Trace ta signature puis valide.</p>
    <canvas id="pad" data-written-signature-target="canvas" width="320"
    height="150"></canvas>
    <button id="save" data-live-action-param="signed" class="primary"
    style="margin-top:12px">Enregistrer</button>
    <div class="swal2-html-container"></div>
  </div>
</div>
"""

CLOSED_ATTENDANCE = (
    '<div class="card"><p class="status closed">Aucun emargement en cours</p>'
    '<p class="muted">Ouvre un emargement depuis /admin pour tester.</p></div>'
)

DASHBOARD_BODY = """
<header>
  <h1>CESAR Emineo</h1>
  <nav><a href="/admin">Administration</a><a
  href="/connexion?logout=1">Deconnexion</a></nav>
</header>
<main>
  <div class="card toastui-calendar-day-view">
    <p class="muted">Tableau de bord de demonstration. Le bouton n'apparait
    qu'apres
    un rafraichissement de la page, comme sur le site reel.</p>
    <div class="calendar">
      <div class="slot"><strong>Lundi</strong>Culture generale</div>
      <div class="slot"><strong>Mardi</strong>Maths</div>
      <div class="slot"><strong>Mercredi</strong>Anglais</div>
      <div class="slot"><strong>Jeudi</strong>Developpement</div>
      <div class="slot"><strong>Vendredi</strong>Projet</div>
    </div>
  </div>
  <div style="height:18px"></div>
  {attendance}
</main>
{modal}
"""


def _signed_attendance(state: AttendanceState) -> str:
    return (
        '<div class="card"><p class="status open">Presence signee</p>'
        f'<p class="muted">Emargement enregistre a {state.signed_at} '
        f"({state.signature_points} points de signature).</p></div>"
    )


def _open_attendance(state: AttendanceState, run_id: str) -> str:
    return f"""
<div class="card">
  <p class="status open">Emargement ouvert</p>
  <p class="muted">Session {state.session_id}. Le formateur attend ta
  signature.</p>
  <button class="buttonPresent success"
  data-live-action-param="session-{state.session_id}-{run_id}"
          style="margin-top:12px">Signer ma presence</button>
</div>
"""


def _dashboard_parts(state: AttendanceState, run_id: str) -> tuple[str, str]:
    if state.signed:
        return _signed_attendance(state), ""
    if state.open:
        return _open_attendance(state, run_id), OPEN_MODAL
    return CLOSED_ATTENDANCE, ""


def render_dashboard(
    state: AttendanceState,
    run_id: str,
    close_delay_ms: int = 0,
    variants: frozenset[str] = frozenset(),
) -> bytes:
    return _dashboard_page(state, run_id, close_delay_ms, variants)


def _dashboard_page(state, run_id, close_delay_ms, variants) -> bytes:
    attendance, modal = _dashboard_parts(state, run_id)
    body = DASHBOARD_BODY.format(attendance=attendance, modal=modal)
    script = dashboard_script(close_delay_ms, variants)
    return render_page(
        "CESAR - tableau de bord",
        body,
        script=script,
        style=modal_style(variants),
    )


def dashboard_script(close_delay_ms: int, variants: frozenset[str]) -> str:
    return DASHBOARD_SCRIPT.replace(
        "__ATTENDANCE_CLOSE_DELAY_MS__", str(max(0, close_delay_ms))
    ).replace("__CANVAS_WIRING__", canvas_wiring(variants))


def modal_style(variants: frozenset[str]) -> str:
    if SLOW_ANIMATION not in variants:
        return ""
    return MODAL_ANIMATION_STYLE


ADMIN_BODY = """
<header>
  <h1>Administration de l'emulateur</h1>
  <nav><a href="/">Tableau de bord</a></nav>
</header>
<main>
  <div class="card">
    <p>Etat de l'emargement : {badge}</p>
    <p>Signature : {signed} ({points} points, session {session})</p>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:18px">
      <button class="success" onclick="action('open')">Ouvrir
      l'emargement</button>
      <button class="ghost" onclick="action('close')">Fermer</button>
      <button class="danger" onclick="action('reset')">Reinitialiser</button>
    </div>
    <p class="muted" style="margin-top:18px">
      Ouvrir l'emargement incremente la session et remet la signature a zero.
      Le watcher doit rafraichir la page pour voir le bouton.
    </p>
  </div>
</main>
<script>
  async function action(name) {{
    await fetch('/api/attendance/' + name, {{ method: 'POST' }});
    location.reload();
  }}
</script>
"""


def _badge(state: AttendanceState) -> str:
    if state.open:
        return '<span class="status open">ouvert</span>'
    return '<span class="status closed">ferme</span>'


def _signed_badge(state: AttendanceState) -> str:
    if state.signed:
        return f'<span class="status open">signe a {state.signed_at}</span>'
    return '<span class="status closed">non signe</span>'


def render_admin(state: AttendanceState) -> bytes:
    body = ADMIN_BODY.format(
        badge=_badge(state),
        signed=_signed_badge(state),
        points=state.signature_points,
        session=state.session_id,
    )
    return render_page("CESAR - administration", body)


class Handler(BaseHTTPRequestHandler):
    server_version = "CesarEmulator/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    # --- helpers ---

    @property
    def emulator(self) -> Emulator:
        assert EMULATOR is not None
        return EMULATOR

    def cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE_NAME:
                return value
        return None

    def is_authenticated(self) -> bool:
        return self.cookie_token() == self.emulator.token

    def send_html(
        self, payload: bytes, status: int = 200, headers: dict | None = None
    ) -> None:
        self.send_bytes(payload, "text/html; charset=utf-8", status, headers)

    def send_bytes(self, payload, content_type, status=200, headers=None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str, *, clear_cookie: bool = False) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if clear_cookie:
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax",
            )
        self.end_headers()

    def read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # --- routes ---

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        self._route_get(parsed.path, parse_qs(parsed.query))

    def _route_get(self, path: str, query: dict) -> None:
        if self._route_public(path):
            return
        if self._route_page(path, query):
            return
        self._serve_asset(path)

    def _route_page(self, path: str, query: dict) -> bool:
        if path == "/connexion":
            self._serve_login(query)
            return True
        if path == "/admin":
            self.send_html(render_admin(self.emulator.state))
            return True
        if path == "/":
            self._serve_dashboard()
            return True
        return False

    def _route_public(self, path: str) -> bool:
        if path == "/api/state":
            self.send_json(self.emulator.as_dict())
            return True
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return True
        return False

    def _serve_login(self, query: dict) -> None:
        if "logout" in query:
            self.redirect("/connexion", clear_cookie=True)
            return
        if self.is_authenticated():
            self.redirect("/")
            return
        page = scenario_page("/connexion")
        if page is None:
            page = render_login(error="error" in query)
        self.send_html(page)

    def _serve_dashboard(self) -> None:
        if not self.is_authenticated():
            self.redirect("/connexion")
            return
        page = scenario_page("/")
        if page is None:
            page = self._dashboard_page()
        self.send_html(page)

    def _dashboard_page(self) -> bytes:
        return render_dashboard(
            self.emulator.state,
            self.emulator.run_id,
            self.emulator.attendance_close_delay_ms,
            self.emulator.variants,
        )

    def _serve_asset(self, path: str) -> None:
        asset = scenario_asset(path)
        if asset is not None:
            self.send_bytes(*asset)
            return
        self.send_html(b"<h1>404</h1>", status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/connexion":
            return self._post_login()
        if path == "/api/signature":
            return self._post_signature()
        if path.startswith("/api/attendance/"):
            return self._post_attendance(path)
        self.send_json({"error": "route inconnue"}, status=404)

    def _post_login(self) -> None:
        username, password = self._login_fields()
        if username != self.emulator.username or password != self.emulator.password:
            self.redirect("/connexion?error=1")
            return
        self._send_login_cookie()

    def _login_fields(self) -> tuple[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(raw)
        # Un scenario capture reprend les noms de champs de CESAR.
        username = (form.get("username") or form.get("_username") or [""])[0]
        password = (form.get("password") or form.get("_password") or [""])[0]
        return username, password

    def _send_login_cookie(self) -> None:
        cookie = f"{COOKIE_NAME}={self.emulator.token}; Path=/; HttpOnly; SameSite=Lax"
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _signature_points_from_payload(self, payload) -> list | None:
        if payload is None:
            self._reject(400, "Corps JSON invalide.")
            return None
        points = payload.get("points")
        if not isinstance(points, list) or not points:
            self._reject(400, "Signature vide.")
            return None
        return points

    def _read_signature_points(self) -> list | None:
        if not self.is_authenticated():
            self._reject(401, "Session expiree.")
            return None
        payload = self.read_json()
        return self._signature_points_from_payload(payload)

    def _post_signature(self) -> None:
        points = self._read_signature_points()
        if points is None:
            return
        ok, message = self.emulator.sign(points)
        self.send_json(
            {"success": ok, "message": message},
            status=200 if ok else 409,
        )

    def _reject(self, status: int, message: str) -> None:
        self.send_json({"message": message}, status=status)

    def _post_attendance(self, path: str) -> None:
        action = path.rsplit("/", 1)[-1]
        if not self._attendance_action(action):
            self.send_json({"error": "action inconnue"}, status=404)
            return
        self.send_json({"ok": True, **self.emulator.as_dict()})

    def _attendance_action(self, action: str) -> bool:
        actions = {
            "open": self.emulator.open_attendance,
            "close": self.emulator.close_attendance,
            "reset": self.emulator.reset,
        }
        handler = actions.get(action)
        if handler is None:
            return False
        handler()
        return True


def _afficher_erreur_scenario(exc: ScenarioError) -> None:
    print(f"Scenario invalide : {exc}", file=sys.stderr)


def _afficher_port_occupe(args) -> None:
    print(f"Port {args.port} deja utilise sur {args.host}.", file=sys.stderr)
    print("Verifie qui l'occupe :", file=sys.stderr)
    print(f"  ss -ltnp 'sport = :{args.port}'", file=sys.stderr)
    print("Ou prends un autre port :", file=sys.stderr)
    print(
        f"  python3 emulator/server.py --port {args.port + 1}",
        file=sys.stderr,
    )
    print("Ou laisse le systeme en choisir un :", file=sys.stderr)
    print("  python3 emulator/server.py --port 0", file=sys.stderr)


def _afficher_demarrage(base: str, scenario, args) -> None:
    print(f"Emulateur CESAR demarre sur {base}", flush=True)
    if scenario is not None:
        print(f"  scenario  : {scenario.name} ({scenario.root})", flush=True)
    print(
        f"  connexion : {base}/connexion ({args.username} / {args.password})",
        flush=True,
    )
    print(f"  admin     : {base}/admin", flush=True)
    print(f"  etat      : {base}/api/state", flush=True)
    print(f'  watcher   : base_url = "{base}"', flush=True)


def _afficher_arret(started: float) -> None:
    print(f"\nArret apres {int(time.time() - started)}s")


def _add_network_args(parser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="port d'ecoute (0 = port libre choisi automatiquement)",
    )


def _add_session_args(parser) -> None:
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo")
    parser.add_argument(
        "--open",
        action="store_true",
        help="ouvre un emargement au demarrage",
    )


def _add_delay_arg(parser) -> None:
    parser.add_argument(
        "--attendance-close-delay-ms",
        type=int,
        default=int(os.environ.get("ATTENDANCE_CLOSE_DELAY_MS", "0")),
        help=(
            "delai en millisecondes avant de retirer le bouton d'emargement "
            "apres une signature (defaut : ATTENDANCE_CLOSE_DELAY_MS ou 0)"
        ),
    )


def _add_scenario_arg(parser) -> None:
    parser.add_argument(
        "--scenario",
        type=Path,
        default=None,
        help=(
            "dossier de scenario capture a servir pour /connexion et / "
            "a la place des pages generees (voir emulator/scenario.py)"
        ),
    )


VARIANT_HELP = (
    "variante de comportement, repetable : slow-animation anime "
    "lentement la modale de signature, mouse-events-only fait ignorer "
    "les evenements pointer par le canvas"
)


def _add_variant_arg(parser) -> None:
    parser.add_argument(
        "--variant",
        action="append",
        choices=VARIANT_CHOICES,
        default=[],
        help=VARIANT_HELP,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emulateur local de CESAR Emineo")
    _add_network_args(parser)
    _add_session_args(parser)
    _add_delay_arg(parser)
    _add_scenario_arg(parser)
    _add_variant_arg(parser)
    return parser


def _load_scenario_arg(args) -> int | None:
    global SCENARIO
    if args.scenario is None:
        return None
    try:
        SCENARIO = load_scenario(args.scenario, args.attendance_close_delay_ms)
    except ScenarioError as exc:
        _afficher_erreur_scenario(exc)
        return 2
    return None


def _new_emulator(args) -> Emulator:
    return Emulator(
        args.username,
        args.password,
        secrets.token_urlsafe(24),
        secrets.token_hex(3),
        attendance_close_delay_ms=args.attendance_close_delay_ms,
        variants=frozenset(args.variant),
    )


def _create_emulator(args) -> None:
    global EMULATOR
    EMULATOR = _new_emulator(args)
    if args.open:
        EMULATOR.open_attendance()


def _start_server(args):
    try:
        return ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            _afficher_port_occupe(args)
            return None
        raise


def _serve_forever(server, started: float) -> None:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _afficher_arret(started)


def _serve(server, args) -> int:
    base = f"http://{args.host}:{server.server_address[1]}"
    _afficher_demarrage(base, SCENARIO, args)
    started = time.time()
    try:
        _serve_forever(server, started)
    finally:
        server.server_close()
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    error = _load_scenario_arg(args)
    if error is not None:
        return error
    _create_emulator(args)
    server = _start_server(args)
    if server is None:
        return 1
    return _serve(server, args)


if __name__ == "__main__":
    raise SystemExit(main())
