"""Collecteur de statistiques CheckMate (stdlib uniquement).

Recoit deux evenements anonymes envoyes par l'application :

- ``install`` : premiere installation, une seule fois par identifiant ;
- ``signature`` : une signature reussie.

La base SQLite ne contient ni adresse IP, ni identifiant CESAR, ni contenu de
signature. Seul un identifiant d'installation aleatoire distingue les machines.

Lancement :

    CHECKMATE_INGEST_KEY=... python collector.py

Variables d'environnement :

- ``CHECKMATE_INGEST_KEY`` : cle attendue dans l'en-tete ``X-CheckMate-Key``.
- ``CHECKMATE_STATS_DB`` : chemin du fichier SQLite (defaut ``stats.sqlite3``).
- ``CHECKMATE_DASHBOARD_PASSWORD`` : mot de passe du tableau
  de bord (optionnel).
- ``CHECKMATE_DASHBOARD_USER`` : utilisateur du tableau de bord
  (defaut ``checkmate``).
- ``PORT`` : port d'ecoute (defaut ``8099``).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger("checkmate-stats")

EVENTS = {"install", "signature"}
PLATFORMS = {"windows", "linux", "macos", "other"}
INSTALL_RE = re.compile(r"^[0-9a-f]{8,64}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z.+-]{1,32}$")
MAX_BODY = 4096
RATE_WINDOW = 3600
RATE_LIMIT = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    install_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    os TEXT NOT NULL,
    day TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_install
    ON events(install_id) WHERE name = 'install';
DROP INDEX IF EXISTS one_daily;
CREATE INDEX IF NOT EXISTS by_day ON events(day);
"""

INSERT_EVENT = (
    "INSERT OR IGNORE INTO events "
    "(install_id, name, version, os, day, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
SQL_INSTALLS = (
    "SELECT COUNT(DISTINCT install_id) FROM events "
    "WHERE name = 'install'"
)
SQL_SIGNATURES = "SELECT COUNT(*) FROM events WHERE name = 'signature'"
SQL_SIGNERS = (
    "SELECT COUNT(DISTINCT install_id) FROM events "
    "WHERE name = 'signature'"
)
SQL_SERIES = (
    "SELECT day, COALESCE(SUM(name = 'signature'), 0) AS signatures "
    "FROM events WHERE day >= ? GROUP BY day"
)
SQL_VERSIONS = (
    "SELECT version, COUNT(*) AS installs FROM events "
    "WHERE name = 'install' GROUP BY version "
    "ORDER BY installs DESC, version DESC"
)
SQL_PLATFORMS = (
    "SELECT os, COUNT(*) AS installs FROM events "
    "WHERE name = 'install' GROUP BY os ORDER BY installs DESC"
)


class Store:
    """Acces SQLite, une connexion par operation (serveur multi-thread)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def record(self, install_id, name, version, os_name, *, day=None) -> bool:
        current_day = day or datetime.now(UTC).date().isoformat()
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        values = (install_id, name, version, os_name, current_day, created_at)
        with self._connect() as connection:
            cursor = connection.execute(INSERT_EVENT, values)
            return cursor.rowcount > 0

    def _one(self, query: str, *params) -> int:
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row[0] or 0) if row else 0

    def _rows(self, query: str, *params) -> list[sqlite3.Row]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return list(connection.execute(query, params))

    def _totals(self) -> dict:
        return {
            "installs": self._one(SQL_INSTALLS),
            "signatures": self._one(SQL_SIGNATURES),
            "signers": self._one(SQL_SIGNERS),
        }

    def _series(self, days: int) -> list[dict]:
        start_day = datetime.now(UTC).date() - timedelta(days=days - 1)
        rows = self._rows(SQL_SERIES, start_day.isoformat())
        found = {row["day"]: row for row in rows}
        return [
            self._series_point(start_day, found, offset)
            for offset in range(days)
        ]

    @staticmethod
    def _series_point(start_day, found: dict, offset: int) -> dict:
        day = (start_day + timedelta(days=offset)).isoformat()
        row = found.get(day)
        signatures = int(row["signatures"]) if row else 0
        return {"day": day, "signatures": signatures}

    def _versions(self) -> list[dict]:
        rows = self._rows(SQL_VERSIONS)
        return [
            {"version": row["version"], "installs": int(row["installs"])}
            for row in rows
        ]

    def _platforms(self) -> list[dict]:
        rows = self._rows(SQL_PLATFORMS)
        return [
            {"os": row["os"], "installs": int(row["installs"])}
            for row in rows
        ]

    def summary(self, days: int = 30) -> dict:
        return {
            "totals": self._totals(),
            "series": self._series(days),
            "versions": self._versions(),
            "platforms": self._platforms(),
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }


class RateLimiter:
    def __init__(
        self, limit: int = RATE_LIMIT, window: int = RATE_WINDOW
    ) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


def _event_fields(payload: dict) -> tuple[str, str, str, str]:
    return (
        str(payload.get("install", "")),
        str(payload.get("event", "")),
        str(payload.get("version", "")),
        str(payload.get("os", "")),
    )


def _first_error(fields: tuple[str, str, str, str]) -> str | None:
    install, name, version, platform = fields
    if not INSTALL_RE.fullmatch(install):
        return "bad_install"
    if name not in EVENTS:
        return "bad_event"
    return _platform_error(version, platform)


def _platform_error(version: str, platform: str) -> str | None:
    if not VERSION_RE.fullmatch(version):
        return "bad_version"
    if platform not in PLATFORMS:
        return "bad_os"
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "checkmate-stats"
    store: Store
    ingest_key: str
    dashboard_user: str | None
    dashboard_password: str | None
    limiter: RateLimiter

    def log_message(self, fmt: str, *args) -> None:
        # Pas d'adresse IP dans les journaux.
        logger.info("%s", fmt % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _authorized(self) -> bool:
        if not self.dashboard_password:
            self._json(503, {"error": "dashboard_disabled"})
            return False
        credentials = self._basic_credentials()
        if credentials is None:
            return False
        return self._match_credentials(*credentials)

    def _basic_credentials(self) -> tuple[str, str] | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            self._challenge()
            return None
        decoded = self._decode_basic(header)
        if decoded is None:
            return None
        user, _, password = decoded.partition(":")
        return user, password

    def _decode_basic(self, header: str) -> str | None:
        import base64

        try:
            return base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            self._challenge()
            return None

    def _match_credentials(self, user: str, password: str) -> bool:
        expected_user = self.dashboard_user or ""
        if hmac.compare_digest(user, expected_user) and hmac.compare_digest(
            password, self.dashboard_password
        ):
            return True
        self._challenge()
        return False

    def _challenge(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="CheckMate stats"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"ok": True})
            return
        if self._authorized():
            self._route_get(path)

    def _route_get(self, path: str) -> None:
        if path == "/api/stats":
            self._json(200, self.store.summary())
            return
        if path in {"/", "/stats"}:
            self._serve_dashboard()
            return
        self._json(404, {"error": "not_found"})

    def _serve_dashboard(self) -> None:
        self._send(
            200, DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8"
        )

    def do_POST(self) -> None:
        if not self._post_allowed():
            return
        payload = self._read_payload()
        if payload is not None:
            self._store_event(payload)

    def _post_allowed(self) -> bool:
        if self.path.split("?", 1)[0] != "/api/event":
            self._reject(404, "not_found")
            return False
        if not self.limiter.allow(self.client_address[0]):
            self._reject(429, "rate_limited")
            return False
        return self._ingest_authorized()

    def _reject(self, status: int, error: str) -> None:
        self._json(status, {"error": error})

    def _ingest_authorized(self) -> bool:
        if not self.ingest_key:
            return True
        provided = self.headers.get("X-CheckMate-Key", "")
        if hmac.compare_digest(provided, self.ingest_key):
            return True
        self._reject(401, "bad_key")
        return False

    def _read_length(self) -> int:
        try:
            return int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return 0

    def _read_payload(self) -> dict | None:
        length = self._read_length()
        if length <= 0 or length > MAX_BODY:
            self._reject(400, "bad_size")
            return None
        payload = self._parse_payload(length)
        if not isinstance(payload, dict):
            self._reject(400, "bad_payload")
            return None
        return payload

    def _parse_payload(self, length: int):
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._reject(400, "bad_json")
            return None

    def _store_event(self, payload: dict) -> None:
        fields = _event_fields(payload)
        error = _first_error(fields)
        if error is not None:
            self._reject(400, error)
            return
        inserted = self.store.record(*fields)
        self._json(202, {"ok": True, "duplicate": not inserted})


DASHBOARD_HTML = """<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CheckMate - statistiques</title>
<style>
  :root {
    --bg: #f4f1ea;
    --card: #fffdf8;
    --ink: #1f1b16;
    --muted: #6f665a;
    --line: #e4ddd0;
    --accent: #b4472a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 40px 24px 72px;
    background: var(--bg); color: var(--ink);
    font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI",
    sans-serif;
  }
  main { max-width: 980px; margin: 0 auto; }
  h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.02em; }
  .sub { color: var(--muted); margin-bottom: 32px; }
  .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit,
  minmax(160px, 1fr)); }
  .card { background: var(--card); border: 1px solid var(--line);
  border-radius: 14px; padding: 18px 20px; }
  .label { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); }
  .value { font-size: 32px; font-weight: 650; margin-top: 6px;
  font-variant-numeric: tabular-nums; }
  section { margin-top: 32px; }
  h2 { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
  .chart { display: flex; align-items: flex-end; gap: 4px; height: 160px;
  padding: 16px; background: var(--card); border: 1px solid var(--line);
  border-radius: 14px; }
  .bar { flex: 1; background: var(--accent); border-radius: 3px 3px 0 0;
  min-height: 2px; opacity: .85; }
  .bar:hover { opacity: 1; }
  table { width: 100%; border-collapse: collapse; background: var(--card);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
  th, td { text-align: left; padding: 10px 16px; border-bottom: 1px solid
  var(--line); }
  tr:last-child td { border-bottom: 0; }
  th { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); font-weight: 500; }
  .empty { color: var(--muted); }
</style>
<main>
  <h1>CheckMate</h1>
  <div class="sub" id="updated">Statistiques d'usage anonymes</div>

  <div class="grid">
    <div class="card"><div class="label">Utilisateurs</div><div class="value"
    id="installs">-</div></div>
    <div class="card"><div class="label">Signatures</div><div class="value"
    id="signatures">-</div></div>
    <div class="card"><div class="label">Signataires uniques</div><div
    class="value" id="signers">-</div></div>
  </div>

  <section>
    <h2>Signatures par jour (30 derniers jours)</h2>
    <div class="chart" id="chart"></div>
  </section>

  <section>
    <h2>Versions installees</h2>
    <table><thead><tr><th>Version</th><th>Installations</th></tr></thead><tbody
    id="versions"></tbody></table>
  </section>

  <section>
    <h2>Systemes</h2>
    <table><thead><tr><th>Systeme</th><th>Installations</th></tr></thead><tbody
    id="platforms"></tbody></table>
  </section>
</main>
<script>
function fill(id, value) { document.getElementById(id).textContent = value; }
function table(id, rows, key) {
  const body = document.getElementById(id);
  body.replaceChildren();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 2; td.className = "empty"; td.textContent = "Aucune donnee";
    tr.append(td); body.append(tr); return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    const a = document.createElement("td"); a.textContent = row[key];
    const b = document.createElement("td"); b.textContent = row.installs;
    tr.append(a, b); body.append(tr);
  }
}
fetch("/api/stats", {headers: {"Accept": "application/json"}})
  .then(r => r.ok ? r.json() : Promise.reject(r.status))
  .then(data => {
    fill("installs", data.totals.installs);
    fill("signatures", data.totals.signatures);
    fill("signers", data.totals.signers);
    const max = Math.max(1, ...data.series.map(d => d.signatures));
    const chart = document.getElementById("chart");
    chart.replaceChildren();
    for (const point of data.series) {
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.style.height = (point.signatures / max * 100) + "%";
      bar.title = point.day + " : " + point.signatures + " signature(s)";
      chart.append(bar);
    }
    table("versions", data.versions, "version");
    table("platforms", data.platforms, "os");
    document.getElementById("updated").textContent =
      "Mis a jour le " + new Date(data.updated_at).toLocaleString("fr-FR");
  })
  .catch(() => {
    document.getElementById("updated").textContent =
      "Impossible de charger les statistiques.";
  });
</script>
</html>
"""


def _handler_class(store, ingest_key, dashboard_user, password):
    attributes = {
        "store": store,
        "ingest_key": ingest_key,
        "dashboard_user": dashboard_user,
        "dashboard_password": password,
        "limiter": RateLimiter(),
    }
    return type("BoundHandler", (Handler,), attributes)


def make_server(
    port: int,
    store: Store,
    *,
    ingest_key: str = "",
    dashboard_user: str = "checkmate",
    dashboard_password: str | None = None,
) -> ThreadingHTTPServer:
    handler = _handler_class(
        store, ingest_key, dashboard_user, dashboard_password
    )
    return ThreadingHTTPServer(("0.0.0.0", port), handler)


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _server_from_env() -> tuple[ThreadingHTTPServer, int]:
    port = int(os.environ.get("PORT", "8099"))
    store = Store(os.environ.get("CHECKMATE_STATS_DB", "stats.sqlite3"))
    server = make_server(
        port,
        store,
        ingest_key=os.environ.get("CHECKMATE_INGEST_KEY", ""),
        dashboard_user=os.environ.get("CHECKMATE_DASHBOARD_USER", "checkmate"),
        dashboard_password=(
            os.environ.get("CHECKMATE_DASHBOARD_PASSWORD") or None
        ),
    )
    return server, port


def main() -> int:
    _configure_logging()
    server, port = _server_from_env()
    logger.info("collecteur a l'ecoute sur le port %s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
