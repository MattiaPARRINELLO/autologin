"""Chargement, mise a l'echelle et sauvegarde de la signature."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

VALID_KINDS = ("start", "move", "end")
MIN_PADDING_RATIO = 0.1
MAX_PADDING_RATIO = 1.0
# En dessous de cette etendue, le trace n'est qu'un point (clic sans mouvement).
MIN_EXTENT = 2.0


class SignatureError(Exception):
    """Signature absente, illisible ou invalide."""


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    kind: str = "move"


@dataclass(frozen=True)
class FittedPoint:
    x: float
    y: float


def _coerce_point(raw: object) -> Point:
    if not isinstance(raw, dict):
        raise SignatureError("chaque point doit etre un objet {x, y, type}")
    try:
        x = float(raw["x"])
        y = float(raw["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SignatureError("point sans coordonnees x/y numeriques") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise SignatureError("coordonnees non finies dans la signature")
    kind = str(raw.get("type", raw.get("kind", "move"))).lower()
    if kind not in VALID_KINDS:
        kind = "move"
    return Point(x=x, y=y, kind=kind)


def points_extent(points: list[Point]) -> tuple[float, float]:
    """Largeur et hauteur de la boite englobante du trace."""
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def parse_points(data: object) -> list[Point]:
    """Accepte la liste brute ou un objet exporte (signatureData/points)."""
    if isinstance(data, dict):
        data = data.get("signatureData", data.get("points"))
    if not isinstance(data, list):
        raise SignatureError("la signature doit etre une liste de points")
    points = [_coerce_point(item) for item in data]
    if len(points) < 2:
        raise SignatureError("la signature doit contenir au moins deux points")
    width, height = points_extent(points)
    if max(width, height) < MIN_EXTENT:
        raise SignatureError(
            "la signature est un point : redessine-la en deplacant la souris"
        )
    return points


def load_signature(path: Path) -> list[Point]:
    if not path.is_file():
        raise SignatureError(f"fichier de signature introuvable : {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SignatureError(f"signature JSON invalide : {exc}") from exc
    return parse_points(data)


def save_signature(path: Path, points: list[Point]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"x": round(p.x, 2), "y": round(p.y, 2), "type": p.kind} for p in points]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def fit_points(
    points: list[Point],
    width: float,
    height: float,
    padding_ratio: float = 0.9,
) -> list[FittedPoint]:
    """Centre et met a l'echelle la signature dans un canvas de taille CSS donnee."""
    if not points:
        raise SignatureError("aucun point a mettre a l'echelle")
    if width <= 0 or height <= 0:
        raise SignatureError("dimensions de canvas invalides")
    if not MIN_PADDING_RATIO <= padding_ratio <= MAX_PADDING_RATIO:
        raise SignatureError(
            f"padding_ratio doit etre entre {MIN_PADDING_RATIO} et {MAX_PADDING_RATIO}"
        )

    xs = [p.x for p in points]
    ys = [p.y for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    box_width = max(max_x - min_x, 1.0)
    box_height = max(max_y - min_y, 1.0)

    scale = min(
        (width * padding_ratio) / box_width,
        (height * padding_ratio) / box_height,
    )

    draw_width = box_width * scale
    draw_height = box_height * scale
    offset_x = (width - draw_width) / 2
    offset_y = (height - draw_height) / 2

    fitted = []
    for point in points:
        x = offset_x + (point.x - min_x) * scale
        y = offset_y + (point.y - min_y) * scale
        fitted.append(
            FittedPoint(
                x=min(max(x, 0.0), width),
                y=min(max(y, 0.0), height),
            )
        )
    return fitted
