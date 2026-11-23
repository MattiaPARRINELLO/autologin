from __future__ import annotations

import json

import pytest

from checkmate_watcher import capture


def test_rewrite_assets_ne_touche_que_les_urls_connues():
    html = '<link href="https://cesar.fr/a.css"><img src="https://autre.fr/b.png">'
    mapping = {"https://cesar.fr/a.css": "assets/000-a.css"}

    result = capture.rewrite_assets(html, mapping)

    assert 'href="/assets/000-a.css"' in result
    assert "https://autre.fr/b.png" in result


def test_normalize_login_action_ramene_le_formulaire_sur_connexion():
    html = '<form id="f" action="https://cesar.fr/login/do" method="post"></form>'

    result = capture.normalize_login_action(html)

    assert 'action="/connexion"' in result
    assert "cesar.fr" not in result


def test_rewrite_css_urls_resout_les_chemins_relatifs():
    css = "body{background:url('../img/fond.png')} @font-face{src:url(https://cesar.fr/f.woff2)}"
    mapping = {
        "https://cesar.fr/img/fond.png": "assets/001-fond.png",
        "https://cesar.fr/f.woff2": "assets/002-f.woff2",
    }

    result = capture.rewrite_css_urls(css, "https://cesar.fr/css/app.css", mapping)

    assert 'url("/assets/001-fond.png")' in result
    assert 'url("/assets/002-f.woff2")' in result


def test_rewrite_css_urls_laisse_les_ressources_inconnues():
    css = "body{background:url(/img/inconnu.png)}"

    assert capture.rewrite_css_urls(css, "https://cesar.fr/a.css", {}) == css


def test_strip_har_secrets_retire_cookies_et_corps(tmp_path):
    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://cesar.fr/api?token=abc",
                        "headers": [
                            {"name": "Cookie", "value": "session=secret"},
                            {"name": "Accept", "value": "*/*"},
                        ],
                        "cookies": [{"name": "session", "value": "secret"}],
                        "queryString": [{"name": "token", "value": "abc"}],
                    },
                    "response": {
                        "url": "https://cesar.fr/api/page",
                        "headers": [{"name": "Set-Cookie", "value": "session=secret"}],
                        "content": {"text": "notes privees", "size": 12},
                    },
                }
            ]
        }
    }
    path = tmp_path / "network.har"
    path.write_text(json.dumps(har), encoding="utf-8")

    capture.strip_har_secrets(path)

    cleaned = json.loads(path.read_text(encoding="utf-8"))
    entry = cleaned["log"]["entries"][0]
    assert entry["request"]["url"] == "https://cesar.fr/api"
    assert entry["request"]["headers"] == [{"name": "Accept", "value": "*/*"}]
    assert "cookies" not in entry["request"]
    assert "queryString" not in entry["request"]
    assert entry["response"]["content"] == {"size": 12}
    assert entry["response"]["headers"] == []


def test_strip_har_secrets_ignore_un_har_absent(tmp_path):
    capture.strip_har_secrets(tmp_path / "absent.har")


def test_build_pages_associe_les_etats_du_tableau_de_bord():
    files = {
        "connexion": "pages/connexion.html",
        "tableau-ferme": "pages/tableau-ferme.html",
        "tableau-ouvert": "pages/tableau-ouvert.html",
        "tableau-signe": "pages/tableau-signe.html",
    }

    pages = capture.build_pages(files)

    assert pages["/connexion"] == "pages/connexion.html"
    assert pages["/"] == {
        "default": "pages/tableau-ferme.html",
        "open": "pages/tableau-ouvert.html",
        "signed": "pages/tableau-signe.html",
    }


def test_build_pages_retombe_sur_la_premiere_page_capturee():
    pages = capture.build_pages({"tableau-ouvert": "pages/tableau-ouvert.html"})

    assert pages["/"] == {
        "open": "pages/tableau-ouvert.html",
        "default": "pages/tableau-ouvert.html",
    }


def test_build_pages_refuse_une_capture_vide():
    with pytest.raises(ValueError, match="aucune page"):
        capture.build_pages({})


def test_asset_name_neutre_les_caracteres_suspects():
    name = capture.asset_name("https://cesar.fr/static/img/logo%20ecole.png", 3)

    assert name == "003-logo-20ecole.png"


def test_sanitize_reecrit_pages_css_et_har(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "pages" / "connexion.html").write_text(
        '<form action="https://cesar.fr/login"></form>'
        '<link rel="stylesheet" href="https://cesar.fr/app.css">',
        encoding="utf-8",
    )
    (tmp_path / "assets" / "000-app.css").write_text(
        "body{background:url(https://cesar.fr/fond.png)}", encoding="utf-8"
    )
    (tmp_path / "capture.json").write_text(
        json.dumps(
            {
                "assets": {
                    "https://cesar.fr/app.css": "assets/000-app.css",
                    "https://cesar.fr/fond.png": "assets/001-fond.png",
                }
            }
        ),
        encoding="utf-8",
    )

    capture.sanitize(tmp_path)

    html = (tmp_path / "pages" / "connexion.html").read_text(encoding="utf-8")
    css = (tmp_path / "assets" / "000-app.css").read_text(encoding="utf-8")
    assert 'href="/assets/000-app.css"' in html
    assert 'action="/connexion"' in html
    assert 'url("/assets/001-fond.png")' in css


def test_sanitize_refuse_une_capture_sans_metadonnees(tmp_path):
    with pytest.raises(FileNotFoundError, match="capture introuvable"):
        capture.sanitize(tmp_path)


def test_write_scenario_ecrit_manifeste_et_harness(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "connexion.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    capture.write_scenario(tmp_path, "demo")

    manifest = json.loads((tmp_path / "scenario.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "demo"
    assert manifest["pages"] == {"/connexion": "pages/connexion.html"}
    assert manifest["harness"] == "harness.js"
    assert (tmp_path / "harness.js").is_file()


def test_write_scenario_ne_remplace_pas_un_harness_existant(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "connexion.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    (tmp_path / "harness.js").write_text("// ecrit a la main", encoding="utf-8")

    capture.write_scenario(tmp_path, "demo")

    assert (tmp_path / "harness.js").read_text(encoding="utf-8") == "// ecrit a la main"
