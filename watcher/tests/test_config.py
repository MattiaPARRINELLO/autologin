from __future__ import annotations

import textwrap
from pathlib import Path

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


def test_les_chemins_par_defaut_viennent_de_paths(tmp_path):
    from checkmate_watcher.paths import (
        default_profile_dir,
        default_signature_path,
        default_state_file,
    )

    config = load_config(write_config(tmp_path))
    assert config.watcher.profile_dir == default_profile_dir()
    assert config.watcher.state_file == default_state_file()
    assert config.signature.file == default_signature_path()


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


def test_save_config_retente_apres_verrou(tmp_path, monkeypatch):
    from checkmate_watcher.config import default_config, save_config

    path = tmp_path / "config.toml"
    original = Path.replace
    calls = {"count": 0}

    def flaky(self, target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("fichier verrouille")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    save_config(path, default_config(), password_env="CHECKMATE_PASSWORD")
    assert calls["count"] >= 2
    assert path.is_file()


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


def test_canal_stable_par_defaut(tmp_path):
    config = load_config(write_config(tmp_path))
    assert config.updates.channel == "stable"


def test_lit_le_canal_beta(tmp_path):
    config = load_config(write_config(tmp_path, '[updates]\nchannel = "beta"'))
    assert config.updates.channel == "beta"


def test_alias_include_prerelease(tmp_path):
    config = load_config(write_config(tmp_path, "[updates]\ninclude_prerelease = true"))
    assert config.updates.channel == "beta"
    config = load_config(
        write_config(tmp_path, "[updates]\ninclude_prerelease = false")
    )
    assert config.updates.channel == "stable"


def test_le_canal_prime_sur_l_alias(tmp_path):
    config = load_config(
        write_config(
            tmp_path,
            '[updates]\nchannel = "stable"\ninclude_prerelease = true',
        )
    )
    assert config.updates.channel == "stable"


def test_refuse_un_canal_inconnu(tmp_path):
    with pytest.raises(ConfigError, match="channel doit valoir"):
        load_config(write_config(tmp_path, '[updates]\nchannel = "nightly"'))
