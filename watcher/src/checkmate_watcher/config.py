"""Chargement et validation de la configuration TOML."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Configuration invalide ou incomplete."""


def expand_path(value: str) -> Path:
    """Developpe les variables d'environnement et le ~ d'un chemin."""
    return Path(os.path.expandvars(os.path.expanduser(value)))


DEFAULT_SELECTORS: dict[str, tuple[str, ...]] = {
    "attendance_button": (
        "button.buttonPresent",
        "button[class*='buttonPresent']",
        "button[data-live-action-param*='present']",
    ),
    "signature_canvas": (
        "canvas[data-written-signature-target='canvas']",
        "canvas[data-written-signature-target]",
        ".swal2-container canvas",
    ),
    "signature_save": (
        "button[data-live-action-param='signed']",
        "button[data-live-action-param*='sign']",
        ".swal2-container button.btn-primary",
    ),
    "confirmation": (
        ".swal2-html-container",
        ".swal2-popup .swal2-html-container",
    ),
    "login_username": ("input#username",),
    "login_password": ("input#password",),
    "login_submit": ("button[type='submit'].btn-primary",),
}


@dataclass(frozen=True)
class Selectors:
    attendance_button: tuple[str, ...]
    signature_canvas: tuple[str, ...]
    signature_save: tuple[str, ...]
    confirmation: tuple[str, ...]
    login_username: tuple[str, ...]
    login_password: tuple[str, ...]
    login_submit: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict) -> Selectors:
        values = {}
        for key, default in DEFAULT_SELECTORS.items():
            raw = data.get(key, default)
            if isinstance(raw, str):
                raw = (raw,)
            if not raw or not all(isinstance(item, str) and item for item in raw):
                raise ConfigError(
                    f"selecteurs.{key} doit etre une liste de selecteurs CSS non vides"
                )
            values[key] = tuple(raw)
        return cls(**values)


@dataclass(frozen=True)
class CesarConfig:
    base_url: str
    username: str
    password: str
    login_path: str = "/connexion"
    dashboard_path: str = "/"

    @property
    def login_url(self) -> str:
        return self.base_url.rstrip("/") + self.login_path

    @property
    def dashboard_url(self) -> str:
        return self.base_url.rstrip("/") + self.dashboard_path


@dataclass(frozen=True)
class WatcherConfig:
    poll_interval: int = 60
    dedupe_ttl: int = 3600
    confirm_timeout: int = 180
    auto_sign: bool = False
    auto_sign_delay: int = 20
    headless: bool = False
    executable_path: str | None = None
    profile_dir: Path = Path("~/.local/share/checkmate-watcher/profile")
    state_file: Path = Path("~/.local/share/checkmate-watcher/state.json")


@dataclass(frozen=True)
class SignatureConfig:
    file: Path = Path("~/.config/checkmate-watcher/signature.json")
    padding_ratio: float = 0.9


@dataclass(frozen=True)
class NotificationConfig:
    app_name: str = "CheckMate"
    icon: str = "dialog-information"


@dataclass(frozen=True)
class Config:
    cesar: CesarConfig
    watcher: WatcherConfig
    signature: SignatureConfig
    notifications: NotificationConfig
    selectors: Selectors


def _require(table: dict, key: str, table_name: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[{table_name}] {key} est obligatoire")
    return value.strip()


def _resolve_password(table: dict) -> str:
    direct = table.get("password")
    env_name = table.get("password_env")
    if isinstance(env_name, str) and env_name:
        value = os.environ.get(env_name)
        if value is None:
            raise ConfigError(f"variable d'environnement {env_name} introuvable")
        return value
    if isinstance(direct, str) and direct:
        return direct
    raise ConfigError("[cesar] password ou password_env est obligatoire")


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"fichier de configuration introuvable : {config_path}")

    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    cesar_table = data.get("cesar", {})
    watcher_table = data.get("watcher", {})
    signature_table = data.get("signature", {})
    notification_table = data.get("notifications", {})
    selectors_table = data.get("selectors", {})

    if not isinstance(cesar_table, dict):
        raise ConfigError("[cesar] doit etre une table TOML")

    cesar = CesarConfig(
        base_url=_require(cesar_table, "base_url", "cesar").rstrip("/"),
        username=_require(cesar_table, "username", "cesar"),
        password=_resolve_password(cesar_table),
        login_path=str(cesar_table.get("login_path", "/connexion")),
        dashboard_path=str(cesar_table.get("dashboard_path", "/")),
    )

    if not cesar.base_url.startswith(("http://", "https://")):
        raise ConfigError("[cesar] base_url doit commencer par http:// ou https://")

    watcher = WatcherConfig(
        poll_interval=int(watcher_table.get("poll_interval", 60)),
        dedupe_ttl=int(watcher_table.get("dedupe_ttl", 3600)),
        confirm_timeout=int(watcher_table.get("confirm_timeout", 180)),
        auto_sign=bool(watcher_table.get("auto_sign", False)),
        auto_sign_delay=int(watcher_table.get("auto_sign_delay", 20)),
        headless=bool(watcher_table.get("headless", False)),
        executable_path=(
            str(watcher_table["executable_path"])
            if watcher_table.get("executable_path")
            else None
        ),
        profile_dir=expand_path(
            str(
                watcher_table.get(
                    "profile_dir", "~/.local/share/checkmate-watcher/profile"
                )
            )
        ),
        state_file=expand_path(
            str(
                watcher_table.get(
                    "state_file", "~/.local/share/checkmate-watcher/state.json"
                )
            )
        ),
    )

    signature = SignatureConfig(
        file=expand_path(
            str(
                signature_table.get(
                    "file", "~/.config/checkmate-watcher/signature.json"
                )
            )
        ),
        padding_ratio=float(signature_table.get("padding_ratio", 0.9)),
    )

    notifications = NotificationConfig(
        app_name=str(notification_table.get("app_name", "CheckMate")),
        icon=str(notification_table.get("icon", "dialog-information")),
    )

    selectors = Selectors.from_dict(selectors_table)

    if watcher.poll_interval < 15:
        raise ConfigError("[watcher] poll_interval doit etre >= 15 secondes")
    if watcher.confirm_timeout < 10:
        raise ConfigError("[watcher] confirm_timeout doit etre >= 10 secondes")
    if not 0.1 <= signature.padding_ratio <= 1.0:
        raise ConfigError("[signature] padding_ratio doit etre entre 0.1 et 1.0")

    return Config(
        cesar=cesar,
        watcher=watcher,
        signature=signature,
        notifications=notifications,
        selectors=selectors,
    )
