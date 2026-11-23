"""Capture d'un parcours CESAR reel, assainissement et ecriture du scenario.

Le parcours se capture en trois temps, sans jamais committer les captures
brutes :

1. ``CaptureSession`` pilote un navigateur visible et enregistre, a chaque
   etape validee par l'operateur, le HTML de la page, ses ressources
   statiques, un HAR et une trace Playwright.
2. ``sanitize`` neutralise les secrets (cookies, jetons, corps des reponses),
   reecrit les references vers ``/assets/`` et ramene le formulaire de
   connexion sur ``/connexion`` pour que le scenario reste servable en local.
3. ``write_scenario`` ecrit ``scenario.json`` et un ``harness.js`` de depart,
   directement consommables par ``emulator/server.py --scenario``.

Le trace Playwright reste local : il contient le DOM reel et les formulaires
saisis. Seules les pages et les assets assainis peuvent etre versionnes.

Lancement interactif :

    uv run python -m checkmate_watcher.capture --output captures/2026-11-20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .browser import resolve_launch_options

HAR_NAME = "network.har"
TRACE_NAME = "trace.zip"
METADATA_NAME = "capture.json"
HARNESS_NAME = "harness.js"
PAGES_DIR = "pages"
ASSETS_DIR = "assets"

ASSET_RESOURCE_TYPES = frozenset({"stylesheet", "script", "font", "image"})
SECRET_HEADERS = frozenset(
    {"cookie", "set-cookie", "authorization", "proxy-authorization"}
)
SECRET_CONTENT_KEYS = frozenset({"mimeType", "size", "compression"})

STEP_CONNEXION = "connexion"
STEP_DASHBOARD = "accueil"
STEP_SIGNATURE = "signature"
STEP_CONFIRMATION = "confirmation"
STEP_SIGNED = "accueil-signe"

STEPS = (
    (STEP_CONNEXION, "Arrive sur la page de connexion, sans te connecter"),
    (
        STEP_DASHBOARD,
        "Connecte-toi, puis attends le tableau de bord avec le bouton d'emargement",
    ),
    (
        STEP_SIGNATURE,
        "Clique sur le bouton d'emargement pour ouvrir la signature",
    ),
    (
        STEP_CONFIRMATION,
        "Signe puis clique sur Enregistrer, sans fermer le message",
    ),
    (
        STEP_SIGNED,
        "Ferme le message et reviens au tableau de bord sans bouton d'emargement",
    ),
)

# Le vrai parcours n'a pas de page « emargement ferme » distincte : le tableau
# de bord sans bouton est le meme avant le lancement de l'emargement et apres
# la signature. Il sert donc d'etat par defaut et d'etat signe.
DASHBOARD_STEPS = {
    STEP_DASHBOARD: ("open",),
    STEP_SIGNED: ("default", "signed"),
}

# Pages conservees comme reference pour ecrire le harness, mais non servies :
# la signature et le message de confirmation sont des popups, pas des routes.
REFERENCE_STEPS = (STEP_SIGNATURE, STEP_CONFIRMATION)

MASK_JS = """
(selectors) => {
  const clone = document.documentElement.cloneNode(true);
  for (const selector of selectors) {
    for (const node of clone.querySelectorAll(selector)) {
      node.textContent = '[masque]';
      for (const attribute of ['value', 'content', 'title', 'alt']) {
        node.removeAttribute(attribute);
      }
    }
  }
  return clone.outerHTML;
}
"""

# Metadonnees que CESAR injecte dans l'en-tete et qui identifient l'etudiant :
# identifiant, nom, jeton CSRF. Retirees de toutes les pages assainies.
SENSITIVE_META = re.compile(
    r'<meta\b[^>]*\bname="(?:app-user|user|csrf[^"]*)"[^>]*>', re.IGNORECASE
)

FORM_ACTION = re.compile(r'(<form\b[^>]*\baction=")([^"]*)(")', re.IGNORECASE)
CSS_URL = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)")

HARNESS_TEMPLATE = """/* Script de liaison du scenario.

   Le JavaScript du vrai CESAR ne connait pas les routes de l'emulateur :
   adapte ce fichier pour ouvrir la modale, tracer et enregistrer sur
   /api/signature. Il est injecte avant </body> dans chaque page servie.

   Voir emulator/scenarios/cesar-simplifie/harness.js pour un exemple complet.
   L'emulateur ne sert que /assets/, /admin et /api/* en plus des pages. */
"""


@dataclass
class CaptureSession:
    root: Path
    base_url: str
    assets: dict[str, str] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    page: object | None = None
    _browser: object | None = None
    _context: object | None = None
    _playwright: object | None = None
    _pending: list = field(default_factory=list)

    async def start(self, headless: bool = False) -> None:
        from playwright.async_api import async_playwright

        (self.root / PAGES_DIR).mkdir(parents=True, exist_ok=True)
        (self.root / ASSETS_DIR).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        options = resolve_launch_options(self._playwright.chromium, None).as_kwargs()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--no-first-run", "--no-default-browser-check"],
            **options,
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 900},
            record_har_path=str(self.root / HAR_NAME),
        )
        await self._context.tracing.start(screenshots=True, snapshots=True)
        self.page = await self._context.new_page()
        self.page.on("response", self._on_response)

    async def goto(self, path: str) -> None:
        if self.page is None:
            raise RuntimeError("capture non demarree")
        await self.page.goto(self.base_url + path, wait_until="networkidle")

    async def save_step(self, name: str, mask_selectors: Sequence[str] = ()) -> Path:
        if self.page is None:
            raise RuntimeError("capture non demarree")
        body = await self.page.evaluate(MASK_JS, list(mask_selectors))
        path = self.root / PAGES_DIR / f"{name}.html"
        path.write_text("<!doctype html>\n" + body, encoding="utf-8")
        self.steps.append(name)
        return path

    async def close(self) -> None:
        await asyncio.gather(*self._pending, return_exceptions=True)
        if self._context is not None:
            await self._context.tracing.stop(path=str(self.root / TRACE_NAME))
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self.write_metadata()

    def write_metadata(self) -> None:
        metadata = {
            "base_url": self.base_url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "steps": self.steps,
            "assets": self.assets,
        }
        path = self.root / METADATA_NAME
        path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def _on_response(self, response) -> None:
        task = asyncio.create_task(self._store_response(response))
        self._pending.append(task)

    async def _store_response(self, response) -> None:
        if response.status != 200 or response.url in self.assets:
            return
        if response.request.resource_type not in ASSET_RESOURCE_TYPES:
            return
        if not response.url.startswith(self.base_url + "/"):
            return
        try:
            body = await response.body()
        except Exception:  # noqa: BLE001
            return
        relative = f"{ASSETS_DIR}/{asset_name(response.url, len(self.assets))}"
        (self.root / relative).write_bytes(body)
        self.assets[response.url] = relative


def asset_name(url: str, index: int) -> str:
    name = Path(urlparse(url).path).name or "ressource"
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:60]
    return f"{index:03d}-{safe}"


def sanitize(root: Path) -> None:
    capture = read_metadata(root)
    rewrite_pages(root, capture["assets"])
    rewrite_stylesheets(root, capture["assets"])
    strip_har_secrets(root / HAR_NAME)


def read_metadata(root: Path) -> dict:
    path = root / METADATA_NAME
    if not path.is_file():
        raise FileNotFoundError(f"capture introuvable : {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite_pages(root: Path, mapping: dict[str, str]) -> None:
    for page in sorted((root / PAGES_DIR).glob("*.html")):
        html = rewrite_assets(page.read_text(encoding="utf-8"), mapping)
        html = strip_sensitive_meta(html)
        if page.stem == STEP_CONNEXION:
            html = normalize_login_action(html)
        page.write_text(html, encoding="utf-8")


def strip_sensitive_meta(html: str) -> str:
    return SENSITIVE_META.sub("", html)


def rewrite_assets(html: str, mapping: dict[str, str]) -> str:
    for url, relative in mapping.items():
        html = html.replace(url, "/" + relative)
    return html


def normalize_login_action(html: str) -> str:
    return FORM_ACTION.sub(r"\1/connexion\3", html, count=1)


def rewrite_stylesheets(root: Path, mapping: dict[str, str]) -> None:
    origins = {relative: url for url, relative in mapping.items()}
    for relative, origin in origins.items():
        path = root / relative
        if path.suffix != ".css" or not path.is_file():
            continue
        css = path.read_text(encoding="utf-8")
        path.write_text(rewrite_css_urls(css, origin, mapping), encoding="utf-8")


def rewrite_css_urls(css: str, origin: str, mapping: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        absolute = urljoin(origin, match.group(2).strip())
        relative = mapping.get(absolute)
        if relative is None:
            return match.group(0)
        return f'url("/{relative}")'

    return CSS_URL.sub(replace, css)


def strip_har_secrets(path: Path) -> None:
    if not path.is_file():
        return
    har = json.loads(path.read_text(encoding="utf-8"))
    for entry in har.get("log", {}).get("entries", []):
        scrub_message(entry.get("request", {}))
        scrub_message(entry.get("response", {}))
    path.write_text(json.dumps(har, ensure_ascii=False, indent=2), encoding="utf-8")


def scrub_message(message: dict) -> None:
    message["headers"] = [
        header
        for header in message.get("headers", [])
        if header.get("name", "").lower() not in SECRET_HEADERS
    ]
    message.pop("cookies", None)
    message.pop("queryString", None)
    # Le corps d'une requete contient le formulaire de connexion :
    # identifiant, mot de passe en clair et jeton CSRF.
    message.pop("postData", None)
    message["url"] = message.get("url", "").split("?", 1)[0]
    if "content" in message:
        message["content"] = {
            key: value
            for key, value in message["content"].items()
            if key in SECRET_CONTENT_KEYS
        }


def write_scenario(root: Path, name: str) -> Path:
    files = page_files(root)
    manifest = {
        "name": name,
        "pages": build_pages(files),
        "harness": HARNESS_NAME,
        "assets": ASSETS_DIR,
    }
    (root / "scenario.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    harness = root / HARNESS_NAME
    if not harness.exists():
        harness.write_text(HARNESS_TEMPLATE, encoding="utf-8")
    return root


def page_files(root: Path) -> dict[str, str]:
    pages = sorted((root / PAGES_DIR).glob("*.html"))
    return {page.stem: f"{PAGES_DIR}/{page.name}" for page in pages}


def build_pages(files: dict[str, str]) -> dict:
    pages: dict = {}
    if STEP_CONNEXION in files:
        pages["/connexion"] = files[STEP_CONNEXION]
    dashboard = build_dashboard_states(files)
    if dashboard:
        pages["/"] = dashboard
    if not pages:
        raise ValueError("aucune page capturee : capture d'abord un parcours")
    return pages


def build_dashboard_states(files: dict[str, str]) -> dict[str, str]:
    states: dict[str, str] = {}
    for step, step_states in DASHBOARD_STEPS.items():
        for state in step_states:
            if step in files:
                states[state] = files[step]
    if states:
        states.setdefault("default", next(iter(states.values())))
    return states


async def run_capture(args: argparse.Namespace) -> None:
    session = CaptureSession(args.output, args.base_url.rstrip("/"))
    await session.start()
    print(f"Capture dans {args.output} (quitte par Ctrl-C a tout moment)")
    try:
        for name, instruction in STEPS:
            print(f"\n[{name}] {instruction}")
            await asyncio.to_thread(input, "Entree pour capturer : ")
            await session.save_step(name, args.mask)
    finally:
        await session.close()
    sanitize(args.output)
    write_scenario(args.output, args.name or args.output.name)
    print(f"\nScenario ecrit dans {args.output}")
    references = [step for step in REFERENCE_STEPS if step in session.steps]
    if references:
        print(f"  captures de reference (non servies) : {', '.join(references)}")
    print(f"  python emulator/server.py --scenario {args.output}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture un parcours CESAR reel et produit un scenario local "
            "assaini, servable par emulator/server.py --scenario"
        )
    )
    parser.add_argument(
        "--base-url",
        default="https://cesar.example.fr",
        help="racine du site a capturer",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures") / datetime.now().strftime("%Y-%m-%d"),
        help="dossier de sortie (ignore par git)",
    )
    parser.add_argument("--name", default=None, help="nom du scenario produit")
    parser.add_argument(
        "--mask",
        action="append",
        default=[],
        help=(
            "selecteur CSS dont le texte doit etre masque dans les pages "
            "capturees (nom, identifiant, cours), repetable"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        asyncio.run(run_capture(args))
    except KeyboardInterrupt:
        print("\nCapture interrompue.", file=sys.stderr)
        return 130
    except (FileNotFoundError, ValueError) as exc:
        print(f"Capture impossible : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
