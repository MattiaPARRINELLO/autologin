from __future__ import annotations

import textwrap

import pytest

from checkmate_watcher.config import ConfigError, load_config


def write_config(tmp_path, extra: str = ""):
    path = tmp_path / "config.toml"
    path.write_text(
        textwrap.dedent(
            f"""
            [cesar]
            base_url = "https://cesar.example.fr/"
            username = "eleve"
            password = "secret"

            {extra}
            """
        ),
        encoding="utf-8",
    )
    return path


def test_charge_les_valeurs_par_defaut(tmp_path):
    config = load_config(write_config(tmp_path))
    assert config.cesar.base_url == "https://cesar.example.fr"
    assert config.cesar.login_url == "https://cesar.example.fr/connexion"
    assert config.watcher.poll_interval == 60
    assert config.watcher.auto_sign is False
    assert config.selectors.attendance_button[0] == "button.buttonPresent"


def test_surcharge_les_valeurs(tmp_path):
    config = load_config(
        write_config(
            tmp_path,
            """
            [watcher]
            poll_interval = 30
            auto_sign = true
            auto_sign_delay = 5
            headless = true

            [signature]
            padding_ratio = 0.5
            """,
        )
    )
    assert config.watcher.poll_interval == 30
    assert config.watcher.auto_sign is True
    assert config.watcher.headless is True
    assert config.signature.padding_ratio == 0.5


def test_refuse_un_intervalle_trop_court(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, "[watcher]\npoll_interval = 5"))


def test_refuse_un_mot_de_passe_absent(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cesar]
base_url = "https://cesar.example.fr"
username = "eleve"
password_env = "VARIABLE_QUI_N_EXISTE_PAS"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_lit_le_mot_de_passe_depuis_l_environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKMATE_TEST_PASSWORD", "depuis-env")
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cesar]
base_url = "https://cesar.example.fr"
username = "eleve"
password_env = "CHECKMATE_TEST_PASSWORD"
""",
        encoding="utf-8",
    )
    assert load_config(path).cesar.password == "depuis-env"


def test_refuse_un_ficher_absent(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")
