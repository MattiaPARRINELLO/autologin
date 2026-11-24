from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from checkmate_watcher import config as config_module
from checkmate_watcher.config import (
    Config,
    ConfigError,
    default_config,
    load_config,
    save_config,
    save_updates_channel,
)


def _config_text(extra: str) -> str:
    return textwrap.dedent(
        f"""
        [cesar]
        base_url = "https://cesar.example.fr/"
        username = "eleve"
        password = "secret"

        {extra}
        """
    )


def write_config(tmp_path, extra: str = ""):
    path = tmp_path / "config.toml"
    path.write_text(_config_text(extra), encoding="utf-8")
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


def _surcharge_watcher_et_signature() -> str:
    return """
            [watcher]
            poll_interval = 30
            auto_sign = true
            auto_sign_delay = 5
            headless = true

            [signature]
            padding_ratio = 0.5
            """


def test_surcharge_les_valeurs(tmp_path):
    config = load_config(write_config(tmp_path, _surcharge_watcher_et_signature()))
    assert config.watcher.poll_interval == 30
    assert config.watcher.auto_sign is True
    assert config.watcher.headless is True
    assert config.signature.padding_ratio == 0.5


def _config_personnalisee() -> Config:
    config = default_config()
    return replace(
        config,
        cesar=replace(config.cesar, username="eleve", password="secret"),
        watcher=replace(config.watcher, executable_path="/opt/chrome", auto_sign=True),
        notifications=replace(config.notifications, enabled=False),
        updates=replace(config.updates, channel="beta"),
    )


def test_save_puis_reload_conserve_toute_la_configuration(tmp_path):
    config = _config_personnalisee()
    path = tmp_path / "config.toml"
    save_config(path, config, password="secret")
    assert load_config(path) == config


def test_refuse_un_intervalle_trop_court(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, "[watcher]\npoll_interval = 5"))


def _fail_once(monkeypatch, method: str, error: Exception):
    original = getattr(Path, method)
    calls = {"count": 0}

    def flaky(self, target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise error
        return original(self, target)

    monkeypatch.setattr(Path, method, flaky)
    return calls


def test_save_config_retente_apres_verrou(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    calls = _fail_once(monkeypatch, "replace", PermissionError("fichier verrouille"))
    save_config(path, default_config(), password_env="CHECKMATE_PASSWORD")
    assert calls["count"] >= 2
    assert path.is_file()


def _write_config_env(tmp_path, variable: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[cesar]\n"
        'base_url = "https://cesar.example.fr"\n'
        'username = "eleve"\n'
        f'password_env = "{variable}"\n',
        encoding="utf-8",
    )
    return path


def test_refuse_un_mot_de_passe_absent(tmp_path):
    path = _write_config_env(tmp_path, "VARIABLE_QUI_N_EXISTE_PAS")
    with pytest.raises(ConfigError):
        load_config(path)


def test_lit_le_mot_de_passe_depuis_l_environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKMATE_TEST_PASSWORD", "depuis-env")
    path = _write_config_env(tmp_path, "CHECKMATE_TEST_PASSWORD")
    assert load_config(path).cesar.password == "depuis-env"


def test_refuse_un_ficher_absent(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")


def test_canal_par_defaut_du_fichier_suit_la_version(tmp_path):
    config = load_config(write_config(tmp_path))
    assert config.updates.channel == config_module._default_channel()


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


def test_save_updates_channel_preserve_le_mot_de_passe(tmp_path):
    path = _write_config_env(tmp_path, "CHECKMATE_TEST_PASSWORD")
    config = save_updates_channel(path, "beta")
    assert config.updates.channel == "beta"
    assert "password_env" in path.read_text(encoding="utf-8")


def test_save_updates_channel_refuse_un_canal_inconnu(tmp_path):
    path = _write_config_env(tmp_path, "CHECKMATE_TEST_PASSWORD")
    with pytest.raises(ConfigError):
        save_updates_channel(path, "nightly")


def test_le_canal_par_defaut_suit_la_version(monkeypatch):
    monkeypatch.setattr(config_module, "__version__", "0.7.0-beta.1")
    assert config_module.UpdatesConfig().channel == "beta"
