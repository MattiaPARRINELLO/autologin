from __future__ import annotations

import textwrap

from checkmate_watcher import credentials
from checkmate_watcher.config import load_config


class FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


class BrokenKeyring:
    def get_password(self, service, username):
        raise RuntimeError("verrouille")

    def set_password(self, service, username, password):
        raise RuntimeError("verrouille")

    def delete_password(self, service, username):
        raise RuntimeError("verrouille")


def test_cycle_de_vie_du_mot_de_passe(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(credentials, "_keyring_module", lambda: fake)

    assert credentials.get_password("checkmate", "eleve") is None
    assert credentials.set_password("checkmate", "eleve", "secret") is True
    assert credentials.get_password("checkmate", "eleve") == "secret"
    assert credentials.delete_password("checkmate", "eleve") is True
    assert credentials.get_password("checkmate", "eleve") is None


def test_trousseau_en_erreur_ne_plante_pas(monkeypatch):
    monkeypatch.setattr(credentials, "_keyring_module", lambda: BrokenKeyring())
    assert credentials.get_password("checkmate", "eleve") is None
    assert credentials.set_password("checkmate", "eleve", "secret") is False
    assert credentials.delete_password("checkmate", "eleve") is False


def _ecrire_config(tmp_path, contenu: str):
    path = tmp_path / "config.toml"
    path.write_text(textwrap.dedent(contenu), encoding="utf-8")
    return path


def _keyring(monkeypatch, valeur):
    monkeypatch.setattr(
        "checkmate_watcher.config.get_keyring_password",
        lambda service, username: valeur,
    )


def test_config_lit_le_mot_de_passe_du_trousseau(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CHECKMATE_TEST_PASSWORD", raising=False)
    _keyring(monkeypatch, "depuis-keyring")
    contenu = (
        '[cesar]\nbase_url = "https://cesar.example.fr"\n'
        'username = "eleve"\npassword_env = "CHECKMATE_TEST_PASSWORD"'
    )
    path = _ecrire_config(tmp_path, contenu)
    assert load_config(path).cesar.password == "depuis-keyring"


def test_config_sans_mot_de_passe_en_mode_onboarding(monkeypatch, tmp_path):
    """Onboarding: aucune source de mot de passe ne doit lever d'erreur."""
    _keyring(monkeypatch, None)
    bloc = '[cesar]\nbase_url = "https://cesar.example.fr"\nusername = "eleve"'
    path = _ecrire_config(tmp_path, bloc)
    config = load_config(path, require_password=False)
    assert config.cesar.password == ""
