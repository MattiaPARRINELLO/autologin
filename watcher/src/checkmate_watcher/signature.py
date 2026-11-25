"""Chargement, mise a l'echelle et sauvegarde de la signature."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

VALID_KINDS = ("start", "move", "end")
MIN_PADDING_RATIO = 0.1
MAX_PADDING_RATIO = 1.0
# Sous cette etendue, le trace n'est qu'un point (clic sans mouvement).
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


def points_extent(points: list[Point]) -> tuple[float, float]:
    """Largeur et hauteur de la boite englobante du trace."""
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _points_list(data: object) -> list:
    if isinstance(data, dict):
        data = data.get("signatureData", data.get("points"))
    if not isinstance(data, list):
        raise SignatureError("la signature doit etre une liste de points")
    return data


def _require_extent(points: list[Point]) -> None:
    if len(points) < 2:
        raise SignatureError("la signature doit contenir au moins deux points")
    width, height = points_extent(points)
    if max(width, height) < MIN_EXTENT:
        raise SignatureError(
            "la signature est un point : redessine-la en deplacant la souris"
        )


def parse_points(data: object) -> list[Point]:
    """Accepte la liste brute ou un objet exporte (signatureData/points)."""
    points = [_coerce_point(item) for item in _points_list(data)]
    _require_extent(points)
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
    payload = [
        {"x": round(p.x, 2), "y": round(p.y, 2), "type": p.kind}
        for p in points
    ]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    path.chmod(0o600)


def _point_coords(raw: object) -> tuple[float, float]:
    if not isinstance(raw, dict):
        raise SignatureError("chaque point doit etre un objet {x, y, type}")
    try:
        x, y = float(raw["x"]), float(raw["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SignatureError("point sans coordonnees x/y numeriques") from exc
    if not (math.isfinite(x) and math.isfinite(y)):
        raise SignatureError("coordonnees non finies dans la signature")
    return x, y


def _point_kind(raw: dict) -> str:
    kind = str(raw.get("type", raw.get("kind", "move"))).lower()
    return kind if kind in VALID_KINDS else "move"


def _coerce_point(raw: object) -> Point:
    x, y = _point_coords(raw)
    return Point(x=x, y=y, kind=_point_kind(raw))


def _require_padding(padding: float) -> None:
    if padding < MIN_PADDING_RATIO or padding > MAX_PADDING_RATIO:
        raise SignatureError(
            f"padding_ratio doit etre entre {MIN_PADDING_RATIO} "
            f"et {MAX_PADDING_RATIO}"
        )


def _require_fit_inputs(
    points, width: float, height: float, padding: float
) -> None:
    if not points:
        raise SignatureError("aucun point a mettre a l'echelle")
    if width <= 0 or height <= 0:
        raise SignatureError("dimensions de canvas invalides")
    _require_padding(padding)


def _bounds(points) -> tuple[float, float, float, float]:
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def _fit_scale(min_x, max_x, min_y, max_y, width, height, padding) -> float:
    box_width = max(max_x - min_x, 1.0)
    box_height = max(max_y - min_y, 1.0)
    return min((width * padding) / box_width, (height * padding) / box_height)


def _fit_offsets(min_x, max_x, min_y, max_y, width, height, padding):
    box_width = max(max_x - min_x, 1.0)
    box_height = max(max_y - min_y, 1.0)
    scale = _fit_scale(min_x, max_x, min_y, max_y, width, height, padding)
    offset_x = (width - box_width * scale) / 2
    offset_y = (height - box_height * scale) / 2
    return offset_x, offset_y, scale


def _fit_point(point, min_x, min_y, offset_x, offset_y, scale, width, height):
    x = offset_x + (point.x - min_x) * scale
    y = offset_y + (point.y - min_y) * scale
    return FittedPoint(x=min(max(x, 0.0), width), y=min(max(y, 0.0), height))


def fit_points(points, width, height, padding_ratio=0.9) -> list[FittedPoint]:
    """Centre et met a l'echelle la signature dans le canvas CSS."""
    _require_fit_inputs(points, width, height, padding_ratio)
    min_x, max_x, min_y, max_y = _bounds(points)
    offset_x, offset_y, scale = _fit_offsets(
        min_x, max_x, min_y, max_y, width, height, padding_ratio
    )
    return [
        _fit_point(p, min_x, min_y, offset_x, offset_y, scale, width, height)
        for p in points
    ]
