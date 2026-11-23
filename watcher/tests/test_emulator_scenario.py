from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "emulator" / "scenario.py"
REFERENCE_SCENARIO = REPO_ROOT / "emulator" / "scenarios" / "cesar-simplifie"


def load_module():
    spec = importlib.util.spec_from_file_location("emulator_scenario", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resout les annotations via sys.modules pendant l'execution.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scenario_module = load_module()


def write_scenario(tmp_path: Path, manifest: dict, **files: str) -> Path:
    (tmp_path / "scenario.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_le_scenario_de_reference_se_charge():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO, 1500)

    assert scenario.name == "cesar-simplifie"
    assert set(scenario.pages) == {"/connexion", "/"}
    assert "__ATTENDANCE_CLOSE_DELAY_MS__" not in scenario.harness
    assert "1500" in scenario.harness


def test_la_page_suit_letat_demargement():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO)

    assert b"Aucun emargement en cours" in scenario.page_html("/", "default")
    assert b'class="buttonPresent' in scenario.page_html("/", "open")
    assert b"Presence signee" in scenario.page_html("/", "signed")
    assert scenario.page_html("/", "etat-inconnu") == scenario.page_html("/", "default")


def test_le_script_de_liaison_est_injecte_avant_la_fin_du_body():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO)

    html = scenario.page_html("/connexion", "default").decode("utf-8")

    assert html.index("submitSignature") < html.index("</body>")


def test_une_route_inconnue_ne_rend_rien():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO)

    assert scenario.page_html("/tableau", "open") is None


def test_les_assets_sont_servis_avec_leur_type():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO)

    payload, content_type = scenario.asset("/assets/cesar.css")

    assert b"--cesar-accent" in payload
    assert content_type == "text/css"


def test_un_asset_hors_du_dossier_est_refuse():
    scenario = scenario_module.load_scenario(REFERENCE_SCENARIO)

    assert scenario.asset("/assets/../../server.py") is None
    assert scenario.asset("/assets/") is None
    assert scenario.asset("/autre/cesar.css") is None


def test_un_manifeste_sans_etat_par_defaut_est_refuse(tmp_path):
    directory = write_scenario(
        tmp_path,
        {"pages": {"/": {"open": "page.html"}}},
        **{"page.html": "<html></html>"},
    )

    with pytest.raises(scenario_module.ScenarioError, match="default"):
        scenario_module.load_scenario(directory)


def test_un_chemin_hors_du_scenario_est_refuse(tmp_path):
    directory = write_scenario(
        tmp_path,
        {"pages": {"/": "../page.html"}},
        **{"page.html": "<html></html>"},
    )

    with pytest.raises(scenario_module.ScenarioError, match="hors du scenario"):
        scenario_module.load_scenario(directory)


def test_un_dossier_absent_est_refuse(tmp_path):
    with pytest.raises(scenario_module.ScenarioError, match="introuvable"):
        scenario_module.load_scenario(tmp_path / "absent")


def test_un_manifeste_illisible_est_refuse(tmp_path):
    (tmp_path / "scenario.json").write_text("{", encoding="utf-8")

    with pytest.raises(scenario_module.ScenarioError, match="illisible"):
        scenario_module.load_scenario(tmp_path)
