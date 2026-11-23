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
    def __init__(
        self,
        username: str,
        password: str,
        token: str,
        run_id: str,
        attendance_close_delay_ms: int = 0,
        variants: frozenset[str] = frozenset(),
    ) -> None:
        self.username = username
        self.password = password
        self.token = token
        self.run_id = run_id
        self.attendance_close_delay_ms = max(0, attendance_close_delay_ms)
        self.variants = frozenset(variants)
        self.lock = threading.Lock()
        self.state = AttendanceState()

    def open_attendance(self) -> AttendanceState:
        with self.lock:
            if not self.state.open:
                self.state.session_id += 1
                self.state.opened_at = datetime.now().isoformat(timespec="seconds")
            self.state.open = True
            self.state.signed = False
            self.state.signature_points = 0
            self.state.signed_at = None
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
            if not points:
                return False, "Signature vide."
            if not self.state.open:
                return False, "Aucun emargement n'est ouvert."
            if self.state.signed:
                return False, "Votre presence est deja enregistree."
            self.state.signed = True
            self.state.signature_points = len(points)
            self.state.signed_at = datetime.now().isoformat(timespec="seconds")
            return True, "Votre presence a bien ete prise en compte."

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
  body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
  header { display: flex; justify-content: space-between; align-items: center;
           padding: 16px 28px; background: #1e293b; border-bottom: 1px solid #334155; }
  header h1 { font-size: 18px; margin: 0; letter-spacing: .3px; }
  header nav a { color: #94a3b8; text-decoration: none; margin-left: 18px; font-size: 14px; }
  header nav a:hover { color: #e2e8f0; }
  main { max-width: 980px; margin: 0 auto; padding: 32px 24px 64px; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 24px; }
  .muted { color: #94a3b8; font-size: 14px; }
  button { font: inherit; border: 0; border-radius: 10px; padding: 12px 20px; cursor: pointer; font-weight: 700; }
  .primary { background: #38bdf8; color: #082f49; }
  .success { background: #22c55e; color: #052e16; }
  .danger { background: #ef4444; color: #450a0a; }
  .ghost { background: #334155; color: #e2e8f0; }
  .calendar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 18px; }
  .slot { background: #0f172a; border: 1px solid #334155; border-radius: 10px;
          padding: 14px 10px; font-size: 13px; color: #94a3b8; min-height: 74px; }
  .slot strong { display: block; color: #e2e8f0; font-size: 14px; margin-bottom: 4px; }
  .status { display: inline-block; padding: 6px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; }
  .status.open { background: #14532d; color: #bbf7d0; }
  .status.closed { background: #334155; color: #cbd5e1; }
  #modal { position: fixed; inset: 0; background: rgba(2, 6, 23, .75);
           display: none; align-items: center; justify-content: center; padding: 20px; }
  #modal.visible { display: flex; }
  .dialog { background: #1e293b; border: 1px solid #334155; border-radius: 18px;
            padding: 24px; width: 380px; box-shadow: 0 30px 80px rgba(0,0,0,.5); }
  canvas { background: #fff; border-radius: 12px; display: block; width: 100%; cursor: crosshair; touch-action: none; }
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


def render_page(title: str, body: str, *, script: str = "", style: str = "") -> bytes:
    extra_style = f"<style>{style}</style>" if style else ""
    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{PAGE_STYLE}</style>
{extra_style}
</head>
<body>
{body}
<script>{script}</script>
</body>
</html>
"""
    return html.encode("utf-8")


def render_login(error: bool = False) -> bytes:
    error_block = (
        '<p style="color:#fca5a5;font-weight:700">Identifiants incorrects.</p>'
        if error
        else ""
    )
    body = f"""
<main style="max-width:420px;margin-top:12vh">
  <div class="card">
    <h1 style="margin-top:0">CESAR Emineo</h1>
    <p class="muted">Emulateur local. Identifiants par defaut : demo / demo.</p>
    {error_block}
    <form method="post" action="/connexion">
      <label class="muted" for="username">Identifiant</label>
      <input id="username" name="username" autocomplete="username"
             style="width:100%;padding:12px;margin:6px 0 16px;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#e2e8f0">
      <label class="muted" for="password">Mot de passe</label>
      <input id="password" name="password" type="password" autocomplete="current-password"
             style="width:100%;padding:12px;margin:6px 0 20px;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#e2e8f0">
      <button class="btn-primary primary" type="submit" style="width:100%">Se connecter</button>
    </form>
  </div>
</main>
"""
    return render_page("CESAR - connexion", body)


def render_dashboard(
    state: AttendanceState,
    run_id: str,
    close_delay_ms: int = 0,
    variants: frozenset[str] = frozenset(),
) -> bytes:
    if state.signed:
        attendance = (
            '<div class="card"><p class="status open">Presence signee</p>'
            f'<p class="muted">Emargement enregistre a {state.signed_at} '
            f"({state.signature_points} points de signature).</p></div>"
        )
        modal = ""
    elif state.open:
        attendance = f"""
<div class="card">
  <p class="status open">Emargement ouvert</p>
  <p class="muted">Session {state.session_id}. Le formateur attend ta signature.</p>
  <button class="buttonPresent success" data-live-action-param="session-{state.session_id}-{run_id}"
          style="margin-top:12px">Signer ma presence</button>
</div>
"""
        modal = """
<div id="modal">
  <div class="dialog">
    <h2 style="margin-top:0">Signature de presence</h2>
    <p class="muted">Trace ta signature puis valide.</p>
    <canvas id="pad" data-written-signature-target="canvas" width="320" height="150"></canvas>
    <button id="save" data-live-action-param="signed" class="primary" style="margin-top:12px">Enregistrer</button>
    <div class="swal2-html-container"></div>
  </div>
</div>
"""
    else:
        attendance = (
            '<div class="card"><p class="status closed">Aucun emargement en cours</p>'
            '<p class="muted">Ouvre un emargement depuis /admin pour tester.</p></div>'
        )
        modal = ""

    body = f"""
<header>
  <h1>CESAR Emineo</h1>
  <nav><a href="/admin">Administration</a><a href="/connexion?logout=1">Deconnexion</a></nav>
</header>
<main>
  <div class="card toastui-calendar-day-view">
    <p class="muted">Tableau de bord de demonstration. Le bouton n'apparait qu'apres
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
    script = dashboard_script(close_delay_ms, variants)
    return render_page(
        "CESAR - tableau de bord", body, script=script, style=modal_style(variants)
    )


def dashboard_script(close_delay_ms: int, variants: frozenset[str]) -> str:
    return DASHBOARD_SCRIPT.replace(
        "__ATTENDANCE_CLOSE_DELAY_MS__", str(max(0, close_delay_ms))
    ).replace("__CANVAS_WIRING__", canvas_wiring(variants))


def modal_style(variants: frozenset[str]) -> str:
    if SLOW_ANIMATION not in variants:
        return ""
    return MODAL_ANIMATION_STYLE


def render_admin(state: AttendanceState) -> bytes:
    badge = (
        '<span class="status open">ouvert</span>'
        if state.open
        else '<span class="status closed">ferme</span>'
    )
    signed = (
        f'<span class="status open">signe a {state.signed_at}</span>'
        if state.signed
        else '<span class="status closed">non signe</span>'
    )
    body = f"""
<header>
  <h1>Administration de l'emulateur</h1>
  <nav><a href="/">Tableau de bord</a></nav>
</header>
<main>
  <div class="card">
    <p>Etat de l'emargement : {badge}</p>
    <p>Signature : {signed} ({state.signature_points} points, session {state.session_id})</p>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:18px">
      <button class="success" onclick="action('open')">Ouvrir l'emargement</button>
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

    def send_bytes(
        self,
        payload: bytes,
        content_type: str,
        status: int = 200,
        headers: dict | None = None,
    ) -> None:
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
        path = parsed.path

        if path == "/api/state":
            self.send_json(self.emulator.as_dict())
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path == "/connexion":
            query = parse_qs(parsed.query)
            if "logout" in query:
                self.redirect("/connexion", clear_cookie=True)
                return
            if self.is_authenticated():
                self.redirect("/")
                return
            page = scenario_page(path)
            if page is None:
                page = render_login(error="error" in query)
            self.send_html(page)
            return

        if path == "/admin":
            self.send_html(render_admin(self.emulator.state))
            return

        if path == "/":
            if not self.is_authenticated():
                self.redirect("/connexion")
                return
            page = scenario_page(path)
            if page is None:
                page = render_dashboard(
                    self.emulator.state,
                    self.emulator.run_id,
                    self.emulator.attendance_close_delay_ms,
                    self.emulator.variants,
                )
            self.send_html(page)
            return

        asset = scenario_asset(path)
        if asset is not None:
            self.send_bytes(*asset)
            return

        self.send_html(b"<h1>404</h1>", status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/connexion":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            form = parse_qs(raw)
            # Un scenario capture reprend les noms de champs de CESAR
            # (_username, _password) : on accepte les deux conventions.
            username = (form.get("username") or form.get("_username") or [""])[0]
            password = (form.get("password") or form.get("_password") or [""])[0]
            if (
                username == self.emulator.username
                and password == self.emulator.password
            ):
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"{COOKIE_NAME}={self.emulator.token}; Path=/; HttpOnly; SameSite=Lax",
                )
                self.end_headers()
            else:
                self.redirect("/connexion?error=1")
            return

        if path == "/api/signature":
            if not self.is_authenticated():
                self.send_json({"message": "Session expiree."}, status=401)
                return
            payload = self.read_json()
            if payload is None:
                self.send_json({"message": "Corps JSON invalide."}, status=400)
                return
            points = payload.get("points")
            if not isinstance(points, list) or not points:
                self.send_json({"message": "Signature vide."}, status=400)
                return
            ok, message = self.emulator.sign(points)
            self.send_json(
                {"success": ok, "message": message}, status=200 if ok else 409
            )
            return

        if path.startswith("/api/attendance/"):
            action_name = path.rsplit("/", 1)[-1]
            if action_name == "open":
                self.emulator.open_attendance()
            elif action_name == "close":
                self.emulator.close_attendance()
            elif action_name == "reset":
                self.emulator.reset()
            else:
                self.send_json({"error": "action inconnue"}, status=404)
                return
            self.send_json({"ok": True, **self.emulator.as_dict()})
            return

        self.send_json({"error": "route inconnue"}, status=404)


def main() -> int:
    global EMULATOR, SCENARIO

    parser = argparse.ArgumentParser(description="Emulateur local de CESAR Emineo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="port d'ecoute (0 = port libre choisi automatiquement)",
    )
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="demo")
    parser.add_argument(
        "--open",
        action="store_true",
        help="ouvre un emargement au demarrage",
    )
    parser.add_argument(
        "--attendance-close-delay-ms",
        type=int,
        default=int(os.environ.get("ATTENDANCE_CLOSE_DELAY_MS", "0")),
        help=(
            "delai en millisecondes avant de retirer le bouton d'emargement "
            "apres une signature (defaut : ATTENDANCE_CLOSE_DELAY_MS ou 0)"
        ),
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=None,
        help=(
            "dossier de scenario capture a servir pour /connexion et / "
            "a la place des pages generees (voir emulator/scenario.py)"
        ),
    )
    parser.add_argument(
        "--variant",
        action="append",
        choices=VARIANT_CHOICES,
        default=[],
        help=(
            "variante de comportement, repetable : slow-animation anime "
            "lentement la modale de signature, mouse-events-only fait ignorer "
            "les evenements pointer par le canvas"
        ),
    )
    args = parser.parse_args()

    if args.scenario is not None:
        try:
            SCENARIO = load_scenario(args.scenario, args.attendance_close_delay_ms)
        except ScenarioError as exc:
            print(f"Scenario invalide : {exc}", file=sys.stderr)
            return 2

    EMULATOR = Emulator(
        args.username,
        args.password,
        secrets.token_urlsafe(24),
        secrets.token_hex(3),
        attendance_close_delay_ms=args.attendance_close_delay_ms,
        variants=frozenset(args.variant),
    )
    if args.open:
        EMULATOR.open_attendance()

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"Port {args.port} deja utilise sur {args.host}.", file=sys.stderr)
            print("Verifie qui l'occupe :", file=sys.stderr)
            print(f"  ss -ltnp 'sport = :{args.port}'", file=sys.stderr)
            print("Ou prends un autre port :", file=sys.stderr)
            print(
                f"  python3 emulator/server.py --port {args.port + 1}", file=sys.stderr
            )
            print("Ou laisse le systeme en choisir un :", file=sys.stderr)
            print("  python3 emulator/server.py --port 0", file=sys.stderr)
            return 1
        raise

    base = f"http://{args.host}:{server.server_address[1]}"
    print(f"Emulateur CESAR demarre sur {base}", flush=True)
    if SCENARIO is not None:
        print(f"  scenario  : {SCENARIO.name} ({SCENARIO.root})", flush=True)
    print(
        f"  connexion : {base}/connexion ({args.username} / {args.password})",
        flush=True,
    )
    print(f"  admin     : {base}/admin", flush=True)
    print(f"  etat      : {base}/api/state", flush=True)
    print(f'  watcher   : base_url = "{base}"', flush=True)
    started = time.time()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nArret apres {int(time.time() - started)}s")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
