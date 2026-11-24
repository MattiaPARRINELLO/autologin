from __future__ import annotations

import json
import os

import pytest

from checkmate_watcher.signature import (
    Point,
    SignatureError,
    fit_points,
    load_signature,
    parse_points,
    save_signature,
)


def test_parse_points_accepte_objet_exporte_et_liste_brute():
    points = [
        {"x": 10, "y": 20, "type": "start"},
        {"x": 15, "y": 25, "type": "move"},
        {"x": 20, "y": 30, "type": "end"},
    ]
    assert len(parse_points(points)) == 3
    assert len(parse_points({"signatureData": points})) == 3
    assert parse_points({"points": points})[2].kind == "end"


def test_parse_points_refuse_une_signature_trop_courte():
    with pytest.raises(SignatureError):
        parse_points([{"x": 1, "y": 1, "type": "start"}])


def test_parse_points_refuse_des_coordonnees_invalides():
    with pytest.raises(SignatureError):
        parse_points([{"x": "a", "y": 1}, {"x": 2, "y": 3}])


def test_parse_points_refuse_une_signature_reduite_a_un_point():
    with pytest.raises(SignatureError):
        parse_points(
            [
                {"x": 42, "y": 17, "type": "start"},
                {"x": 42, "y": 17, "type": "end"},
            ]
        )


def _points_ligne() -> list[Point]:
    return [Point(0, 0, "start"), Point(100, 50, "move"), Point(200, 100, "end")]


def _assert_dans_bornes(fitted, largeur, hauteur) -> None:
    assert len(fitted) == 3
    assert all(0 <= p.x <= largeur and 0 <= p.y <= hauteur for p in fitted)


def _centres(fitted) -> tuple[float, float]:
    xs = [p.x for p in fitted]
    ys = [p.y for p in fitted]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def test_fit_points_centre_et_respecte_les_dimensions():
    fitted = fit_points(_points_ligne(), 320, 150, 0.9)
    _assert_dans_bornes(fitted, 320, 150)
    cx, cy = _centres(fitted)
    assert pytest.approx(cx, abs=1) == 160
    assert pytest.approx(cy, abs=1) == 75


def test_fit_points_conserve_le_ratio():
    points = [Point(0, 0, "start"), Point(200, 100, "end")]
    fitted = fit_points(points, 320, 320, 0.9)
    width = max(p.x for p in fitted) - min(p.x for p in fitted)
    height = max(p.y for p in fitted) - min(p.y for p in fitted)
    assert pytest.approx(width / height, rel=0.01) == 2.0


def test_fit_points_refuse_un_canvas_vide():
    with pytest.raises(SignatureError):
        fit_points([Point(0, 0)], 0, 100)


def test_save_et_load_signature(tmp_path):
    path = tmp_path / "signature.json"
    points = [Point(1, 2, "start"), Point(3, 4, "end")]
    save_signature(path, points)
    reloaded = load_signature(path)
    assert [(p.x, p.y, p.kind) for p in reloaded] == [(1, 2, "start"), (3, 4, "end")]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    assert isinstance(json.loads(path.read_text()), list)


def test_load_signature_fichier_absent(tmp_path):
    with pytest.raises(SignatureError):
        load_signature(tmp_path / "absent.json")
