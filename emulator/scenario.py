"""Scenarios captures servis par l'emulateur CESAR.

Un scenario est un dossier autonome avec :

- un manifeste ``scenario.json`` qui associe chaque route a un fichier HTML,
  par etat d'emargement ;
- un script de liaison ``harness.js`` injecte dans chaque page servie, car le
  JavaScript du vrai CESAR ne connait pas les routes de l'emulateur ;
- un dossier ``assets`` servi tel quel (CSS, polices, images, librairies).

L'emulateur reste maitre de l'etat : ``default``, ``open`` et ``signed``
designent la page servie pour la route demandee.
"""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

MANIFEST_NAME = "scenario.json"
DEFAULT_STATE = "default"
ASSET_PREFIX = "/assets/"
CLOSE_TAG = "</body>"
CLOSE_DELAY_TOKEN = "__ATTENDANCE_CLOSE_DELAY_MS__"


class ScenarioError(Exception):
    """Scenario capture invalide."""


@dataclass(frozen=True)
class Page:
    files: dict[str, Path]

    def file_for(self, state: str) -> Path:
        return self.files.get(state, self.files[DEFAULT_STATE])


@dataclass(frozen=True)
class Scenario:
    name: str
    root: Path
    pages: dict[str, Page]
    harness: str
    assets_dir: Path

    def page_html(self, path: str, state: str) -> bytes | None:
        page = self.pages.get(path)
        if page is None:
            return None
        html = page.file_for(state).read_text("utf-8")
        return inject_harness(html, self.harness).encode("utf-8")

    def asset(self, path: str) -> tuple[bytes, str] | None:
        relative = asset_relative_path(path)
        if relative is None:
            return None
        target = (self.assets_dir / relative).resolve()
        if self.assets_dir not in target.parents or not target.is_file():
            return None
        return target.read_bytes(), mime_type(target)


def inject_harness(html: str, harness: str) -> str:
    block = f"<script>\n{harness}\n</script>\n"
    if CLOSE_TAG not in html:
        return html + block
    return html.replace(CLOSE_TAG, block + CLOSE_TAG, 1)


def asset_relative_path(path: str) -> str | None:
    if not path.startswith(ASSET_PREFIX):
        return None
    relative = path[len(ASSET_PREFIX) :]
    if not relative or ".." in Path(relative).parts:
        return None
    return relative


def mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _scenario_root(directory: Path) -> Path:
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise ScenarioError(f"dossier introuvable : {directory}")
    return root


def _scenario_harness(root: Path, manifest: dict, close_delay_ms: int) -> str:
    relative = manifest.get("harness", "harness.js")
    harness = read_text_file(root, relative, "harness")
    return harness.replace(CLOSE_DELAY_TOKEN, str(max(0, close_delay_ms)))


def _build_scenario(
    root: Path, manifest: dict, close_delay_ms: int
) -> Scenario:
    assets = read_text(manifest, "assets", "assets")
    return Scenario(
        name=read_text(manifest, "name", root.name),
        root=root,
        pages=parse_pages(root, manifest.get("pages")),
        harness=_scenario_harness(root, manifest, close_delay_ms),
        assets_dir=(root / assets).resolve(),
    )


def load_scenario(directory: Path, close_delay_ms: int = 0) -> Scenario:
    root = _scenario_root(directory)
    return _build_scenario(root, read_manifest(root), close_delay_ms)


def read_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as exc:
        raise ScenarioError(f"manifeste absent : {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"manifeste illisible ({path}) : {exc}") from exc
    if not isinstance(data, dict):
        raise ScenarioError(
            f"manifeste invalide ({path}) : objet JSON attendu"
        )
    return data


def read_text(manifest: dict, key: str, default: str) -> str:
    value = manifest.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{key} : chaine non vide attendue")
    return value


def read_text_file(root: Path, relative: object, label: str) -> str:
    return resolve_file(root, relative, label).read_text("utf-8")


def parse_pages(root: Path, raw: object) -> dict[str, Page]:
    if not isinstance(raw, dict) or not raw:
        raise ScenarioError("pages : objet non vide attendu (route -> page)")
    return {
        route: parse_page(root, route, value)
        for route, value in raw.items()
    }


def _page_files(root: Path, route: str, raw: dict) -> dict:
    files = {
        state: resolve_file(root, value, f"pages{route}.{state}")
        for state, value in raw.items()
    }
    if DEFAULT_STATE not in files:
        raise ScenarioError(
            f"pages{route} : etat {DEFAULT_STATE!r} obligatoire"
        )
    return files


def parse_page(root: Path, route: str, raw: object) -> Page:
    if not isinstance(route, str) or not route.startswith("/"):
        raise ScenarioError(f"pages : la route {route!r} doit commencer par /")
    if isinstance(raw, str):
        return Page({DEFAULT_STATE: resolve_file(root, raw, f"pages{route}")})
    if not isinstance(raw, dict) or not raw:
        raise ScenarioError(f"pages{route} : chemin ou objet d'etats attendu")
    return Page(_page_files(root, route, raw))


def resolve_file(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ScenarioError(f"{label} : chemin de fichier attendu")
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ScenarioError(f"{label} : chemin hors du scenario ({relative})")
    if not target.is_file():
        raise ScenarioError(f"{label} : fichier introuvable ({relative})")
    return target
