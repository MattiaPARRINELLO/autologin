"""Chargement et validation de la configuration TOML."""

from __future__ import annotations

import logging
import os
import stat
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from .analytics import DEFAULT_ENDPOINT as DEFAULT_ANALYTICS_ENDPOINT
from .credentials import DEFAULT_SERVICE
from .credentials import get_password as get_keyring_password
from .paths import (
    default_profile_dir,
    default_signature_path,
    default_state_file,
)
from .schedule import (
    DAY_NAMES,
    DEFAULT_DAYS,
    DEFAULT_WINDOWS,
    Schedule,
    ScheduleError,
    parse_days,
    parse_windows,
)
from .signature import MAX_PADDING_RATIO, MIN_PADDING_RATIO
from .updates import BETA_CHANNEL, CHANNELS, STABLE_CHANNEL

logger = logging.getLogger(__name__)


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
    "confirmation": (".swal2-html-container",),
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
    keyring_service: str = DEFAULT_SERVICE
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
    prompt_retry: int = 300
    auto_sign: bool = False
    auto_sign_delay: int = 20
    headless: bool = False
    visible_on_sign: bool = True
    executable_path: str | None = None
    profile_dir: Path = field(default_factory=default_profile_dir)
    state_file: Path = field(default_factory=default_state_file)


@dataclass(frozen=True)
class SignatureConfig:
    file: Path = field(default_factory=default_signature_path)
    padding_ratio: float = 0.9


@dataclass(frozen=True)
class UpdatesConfig:
    enabled: bool = True
    channel: str = STABLE_CHANNEL


@dataclass(frozen=True)
class AnalyticsConfig:
    enabled: bool = True
    endpoint: str = DEFAULT_ANALYTICS_ENDPOINT


def parse_updates_channel(table: dict) -> str:
    """Lit `[updates] channel`, avec `include_prerelease` en alias historique."""
    raw_channel = table.get("channel")
    if raw_channel is None:
        if "include_prerelease" in table:
            return BETA_CHANNEL if bool(table["include_prerelease"]) else STABLE_CHANNEL
        return STABLE_CHANNEL
    channel = str(raw_channel).strip().lower()
    if channel not in CHANNELS:
        values = ", ".join(f"'{item}'" for item in CHANNELS)
        raise ConfigError(f"[updates] channel doit valoir {values}")
    return channel


@dataclass(frozen=True)
class NotificationConfig:
    app_name: str = "CheckMate"
    icon: str = "dialog-information"
    enabled: bool = True


@dataclass(frozen=True)
class Config:
    cesar: CesarConfig
    watcher: WatcherConfig
    signature: SignatureConfig
    notifications: NotificationConfig
    selectors: Selectors
    schedule: Schedule = field(default_factory=Schedule)
    updates: UpdatesConfig = field(default_factory=UpdatesConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)


def _require(table: dict, key: str, table_name: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[{table_name}] {key} est obligatoire")
    return value.strip()


def _resolve_password(
    table: dict, username: str, service: str, required: bool = True
) -> str:
    direct = table.get("password")
    if isinstance(direct, str) and direct:
        return direct

    env_name = table.get("password_env")
    if isinstance(env_name, str) and env_name:
        value = os.environ.get(env_name)
        if value:
            return value
        logger.debug("variable %s absente, essai du trousseau", env_name)

    stored = get_keyring_password(service, username)
    if stored:
        return stored

    if required:
        raise ConfigError(
            "[cesar] mot de passe introuvable : renseigne password ou password_env, "
            "ou lance 'checkmate-watcher set-password'"
        )
    return ""


def default_config() -> Config:
    """Configuration proposee par l'assistant : reglages recommandes."""
    return Config(
        cesar=CesarConfig(
            base_url="https://cesar.emineo-education.fr",
            username="",
            password="",
        ),
        watcher=WatcherConfig(poll_interval=10, headless=True),
        signature=SignatureConfig(),
        notifications=NotificationConfig(),
        selectors=Selectors.from_dict({}),
        schedule=Schedule(
            enabled=True,
            days=parse_days(DEFAULT_DAYS),
            windows=parse_windows(DEFAULT_WINDOWS),
        ),
        updates=UpdatesConfig(),
    )


def _days_to_names(days: tuple[int, ...]) -> list[str]:
    ordered = sorted(DAY_NAMES.items(), key=lambda item: item[1])
    return [name for name, index in ordered if index in days]


def config_to_dict(
    config: Config,
    *,
    password: str | None = None,
    password_env: str | None = None,
) -> dict:
    cesar: dict = {
        "base_url": config.cesar.base_url,
        "login_path": config.cesar.login_path,
        "dashboard_path": config.cesar.dashboard_path,
        "username": config.cesar.username,
        "keyring_service": config.cesar.keyring_service,
    }
    if password:
        cesar["password"] = password
    elif password_env:
        cesar["password_env"] = password_env

    watcher = {
        "poll_interval": config.watcher.poll_interval,
        "dedupe_ttl": config.watcher.dedupe_ttl,
        "confirm_timeout": config.watcher.confirm_timeout,
        "prompt_retry": config.watcher.prompt_retry,
        "auto_sign": config.watcher.auto_sign,
        "auto_sign_delay": config.watcher.auto_sign_delay,
        "headless": config.watcher.headless,
        "visible_on_sign": config.watcher.visible_on_sign,
        "profile_dir": str(config.watcher.profile_dir),
        "state_file": str(config.watcher.state_file),
    }
    if config.watcher.executable_path:
        watcher["executable_path"] = config.watcher.executable_path

    return {
        "cesar": cesar,
        "watcher": watcher,
        "signature": {
            "file": str(config.signature.file),
            "padding_ratio": config.signature.padding_ratio,
        },
        "notifications": {
            "app_name": config.notifications.app_name,
            "icon": config.notifications.icon,
            "enabled": config.notifications.enabled,
        },
        "schedule": {
            "enabled": config.schedule.enabled,
            "days": _days_to_names(config.schedule.days),
            "windows": [str(window) for window in config.schedule.windows],
        },
        "updates": {
            "enabled": config.updates.enabled,
            "channel": config.updates.channel,
        },
        "analytics": {
            "enabled": config.analytics.enabled,
            "endpoint": config.analytics.endpoint,
        },
        "selectors": {
            "attendance_button": list(config.selectors.attendance_button),
            "signature_canvas": list(config.selectors.signature_canvas),
            "signature_save": list(config.selectors.signature_save),
            "confirmation": list(config.selectors.confirmation),
            "login_username": list(config.selectors.login_username),
            "login_password": list(config.selectors.login_password),
            "login_submit": list(config.selectors.login_submit),
        },
    }


def save_config(
    path: str | Path,
    config: Config,
    *,
    password: str | None = None,
    password_env: str | None = None,
) -> Path:
    """Ecrit la configuration de facon atomique, lisible par l'utilisateur seul."""
    target = expand_path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = tomli_w.dumps(
        config_to_dict(config, password=password, password_env=password_env)
    )
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.chmod(0o600)
        last_error: OSError | None = None
        for attempt in range(4):
            if target.exists():
                try:
                    target.chmod(stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
            try:
                temporary.replace(target)
                return target
            except OSError as exc:
                last_error = exc
                logger.warning(
                    "ecriture de la configuration retentee (%s/4) : %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(0.15 * (attempt + 1))
        assert last_error is not None
        raise last_error
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_config(path: str | Path, *, require_password: bool = True) -> Config:
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
    schedule_table = data.get("schedule", {})
    updates_table = data.get("updates", {})

    if not isinstance(cesar_table, dict):
        raise ConfigError("[cesar] doit etre une table TOML")

    username = _require(cesar_table, "username", "cesar")
    keyring_service = str(cesar_table.get("keyring_service", DEFAULT_SERVICE))

    cesar = CesarConfig(
        base_url=_require(cesar_table, "base_url", "cesar").rstrip("/"),
        username=username,
        password=_resolve_password(
            cesar_table, username, keyring_service, required=require_password
        ),
        keyring_service=keyring_service,
        login_path=str(cesar_table.get("login_path", "/connexion")),
        dashboard_path=str(cesar_table.get("dashboard_path", "/")),
    )

    if not cesar.base_url.startswith(("http://", "https://")):
        raise ConfigError("[cesar] base_url doit commencer par http:// ou https://")

    watcher_defaults = WatcherConfig()
    watcher = WatcherConfig(
        poll_interval=int(
            watcher_table.get("poll_interval", watcher_defaults.poll_interval)
        ),
        dedupe_ttl=int(watcher_table.get("dedupe_ttl", watcher_defaults.dedupe_ttl)),
        confirm_timeout=int(
            watcher_table.get("confirm_timeout", watcher_defaults.confirm_timeout)
        ),
        prompt_retry=int(
            watcher_table.get("prompt_retry", watcher_defaults.prompt_retry)
        ),
        auto_sign=bool(watcher_table.get("auto_sign", watcher_defaults.auto_sign)),
        auto_sign_delay=int(
            watcher_table.get("auto_sign_delay", watcher_defaults.auto_sign_delay)
        ),
        headless=bool(watcher_table.get("headless", watcher_defaults.headless)),
        visible_on_sign=bool(
            watcher_table.get("visible_on_sign", watcher_defaults.visible_on_sign)
        ),
        executable_path=(
            str(watcher_table["executable_path"])
            if watcher_table.get("executable_path")
            else None
        ),
        profile_dir=expand_path(
            str(watcher_table.get("profile_dir", watcher_defaults.profile_dir))
        ),
        state_file=expand_path(
            str(watcher_table.get("state_file", watcher_defaults.state_file))
        ),
    )

    signature_defaults = SignatureConfig()
    signature = SignatureConfig(
        file=expand_path(str(signature_table.get("file", signature_defaults.file))),
        padding_ratio=float(
            signature_table.get("padding_ratio", signature_defaults.padding_ratio)
        ),
    )

    notification_defaults = NotificationConfig()
    notifications = NotificationConfig(
        app_name=str(
            notification_table.get("app_name", notification_defaults.app_name)
        ),
        icon=str(notification_table.get("icon", notification_defaults.icon)),
        enabled=bool(notification_table.get("enabled", notification_defaults.enabled)),
    )

    selectors = Selectors.from_dict(selectors_table)
    updates_defaults = UpdatesConfig()
    updates = UpdatesConfig(
        enabled=bool(updates_table.get("enabled", updates_defaults.enabled)),
        channel=parse_updates_channel(updates_table),
    )

    analytics_table = data.get("analytics", {})
    if not isinstance(analytics_table, dict):
        raise ConfigError("[analytics] doit etre une table TOML")
    analytics_defaults = AnalyticsConfig()
    analytics = AnalyticsConfig(
        enabled=bool(analytics_table.get("enabled", analytics_defaults.enabled)),
        endpoint=str(analytics_table.get("endpoint", analytics_defaults.endpoint)),
    )
    if analytics.enabled and not analytics.endpoint.startswith(("http://", "https://")):
        raise ConfigError("[analytics] endpoint doit commencer par http:// ou https://")

    try:
        schedule = Schedule(
            enabled=bool(schedule_table.get("enabled", False)),
            days=parse_days(schedule_table.get("days", DEFAULT_DAYS)),
            windows=parse_windows(schedule_table.get("windows", DEFAULT_WINDOWS)),
        )
    except ScheduleError as exc:
        raise ConfigError(f"[schedule] {exc}") from exc

    if watcher.poll_interval < 10:
        raise ConfigError("[watcher] poll_interval doit etre >= 10 secondes")
    if watcher.confirm_timeout < 10:
        raise ConfigError("[watcher] confirm_timeout doit etre >= 10 secondes")
    if watcher.prompt_retry < 30:
        raise ConfigError("[watcher] prompt_retry doit etre >= 30 secondes")
    if (
        signature.padding_ratio < MIN_PADDING_RATIO
        or signature.padding_ratio > MAX_PADDING_RATIO
    ):
        raise ConfigError(
            f"[signature] padding_ratio doit etre entre "
            f"{MIN_PADDING_RATIO} et {MAX_PADDING_RATIO}"
        )

    return Config(
        cesar=cesar,
        watcher=watcher,
        signature=signature,
        notifications=notifications,
        selectors=selectors,
        schedule=schedule,
        updates=updates,
        analytics=analytics,
    )
