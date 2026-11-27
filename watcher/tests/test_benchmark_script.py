"""Verifie les calculs du harnais de benchmark Rust."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "rust" / "scripts" / "benchmark.py"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "checkmate_benchmark", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _module()

BUDGETS = {
    "budgets": [
        {
            "metric": "startup",
            "aggregate": "p95",
            "max": 100,
            "required": True,
        },
        {"metric": "taille", "aggregate": "max", "max": 10, "required": True},
        {"metric": "ui", "aggregate": "p95", "max": 100, "required": False},
    ]
}


def test_percentile_borne_les_extremes():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert benchmark.percentile(values, 0.0) == 1.0
    assert benchmark.percentile(values, 1.0) == 5.0
    assert benchmark.percentile([7.0], 0.95) == 7.0


def test_aggregate_calcule_median_et_p95():
    result = benchmark.aggregate([1.0, 2.0, 3.0, 4.0, 5.0])

    assert result["median"] == 3.0
    assert result["p95"] == 5.0
    assert result["max"] == 5.0
    assert result["min"] == 1.0


def test_evaluate_passe_sous_les_budgets():
    metrics = {
        "startup": {"p95": 42.0},
        "taille": {"max": 4.0},
        "ui": {"p95": 12.0},
    }

    checks = benchmark.evaluate(metrics, BUDGETS)

    assert [check["status"] for check in checks] == ["pass", "pass", "pass"]


def test_evaluate_echoue_au_dessus_du_budget():
    metrics = {"startup": {"p95": 250.0}, "taille": {"max": 4.0}}
    metrics["ui"] = {"p95": 101.0}

    checks = benchmark.evaluate(metrics, BUDGETS)

    assert checks[0]["status"] == "fail"
    assert checks[1]["status"] == "pass"
    assert checks[2]["status"] == "fail"


def test_evaluate_signale_les_metriques_en_attente():
    checks = benchmark.evaluate({}, BUDGETS)

    assert checks[0]["status"] == "fail"
    assert checks[1]["status"] == "fail"
    assert checks[2]["status"] == "pending"


def test_evaluate_refuse_une_agregation_absente():
    metrics = {"startup": {"max": 1.0}, "taille": {"max": 4.0}}

    checks = benchmark.evaluate(metrics, BUDGETS)

    assert checks[0]["status"] == "fail"
