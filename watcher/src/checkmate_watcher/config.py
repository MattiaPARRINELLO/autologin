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

from . import __version__
from .analytics import DEFAULT_ENDPOINT as DEFAULT_ANALYTICS_ENDPOINT
from .credentials import DEFAULT_SERVICE
from .credentials import get_password as get_keyring_password
from .paths import (
    default_http_cookies_file,
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


def _normalize_selector_list(key: str, raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        raw = (raw,)
    if not raw or not all(isinstance(item, str) and item for item in raw):
        raise ConfigError(
            f"selecteurs.{key} doit etre une liste de selecteurs CSS non vides"
        )
    return tuple(raw)


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
        values = {
            key: _normalize_selector_list(key, data.get(key, default))
            for key, default in DEFAULT_SELECTORS.items()
        }
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
    transport: str = "http"
    auto_sign: bool = False
    auto_sign_delay: int = 20
    headless: bool = False
    visible_on_sign: bool = True
    executable_path: str | None = None
    profile_dir: Path = field(default_factory=default_profile_dir)
    state_file: Path = field(default_factory=default_state_file)
    http_cookies_file: Path = field(default_factory=default_http_cookies_file)


@dataclass(frozen=True)
class SignatureConfig:
    file: Path = field(default_factory=default_signature_path)
    padding_ratio: float = 0.9


def _default_channel() -> str:
    return BETA_CHANNEL if "-beta" in __version__ else STABLE_CHANNEL


@dataclass(frozen=True)
class UpdatesConfig:
    enabled: bool = True
    channel: str = field(default_factory=_default_channel)


@dataclass(frozen=True)
class AnalyticsConfig:
    enabled: bool = True
    endpoint: str = DEFAULT_ANALYTICS_ENDPOINT


def _legacy_channel(table: dict) -> str | None:
    if "include_prerelease" not in table:
        return None
    return (
        BETA_CHANNEL if bool(table["include_prerelease"]) else STABLE_CHANNEL
    )


def _normalize_channel(raw: object) -> str:
    return str(raw).strip().lower()


def _validate_channel(channel: str) -> str:
    if channel not in CHANNELS:
        values = ", ".join(f"'{item}'" for item in CHANNELS)
        raise ConfigError(f"[updates] channel doit valoir {values}")
    return channel


def parse_updates_channel(table: dict) -> str:
    """Lit le canal, avec `include_prerelease` comme alias historique."""
    raw = table.get("channel")
    if raw is None:
        legacy = _legacy_channel(table)
        return _default_channel() if legacy is None else legacy
    return _validate_channel(_normalize_channel(raw))


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


def _direct_password(table: dict) -> str:
    direct = table.get("password")
    if isinstance(direct, str) and direct:
        return direct
    return ""


def _env_password(table: dict) -> str:
    env_name = table.get("password_env")
    if not isinstance(env_name, str) or not env_name:
        return ""
    value = os.environ.get(env_name)
    if value:
        return value
    logger.debug("variable %s absente, essai du trousseau", env_name)
    return ""


def _required_password(required: bool) -> str:
    if required:
        raise ConfigError(
            "[cesar] mot de passe introuvable : renseigne password ou "
            "password_env, ou lance 'checkmate-watcher set-password'"
        )
    return ""


def _resolve_password(
    table: dict, username: str, service: str, required: bool = True
) -> str:
    for source in (
        lambda: _direct_password(table),
        lambda: _env_password(table),
        lambda: get_keyring_password(service, username),
    ):
        if value := source():
            return value
    return _required_password(required)


def _default_cesar() -> CesarConfig:
    return CesarConfig(
        base_url="https://cesar.emineo-education.fr",
        username="",
        password="",
    )


def _default_watcher() -> WatcherConfig:
    return WatcherConfig(poll_interval=10, headless=True)


def _default_schedule() -> Schedule:
    return Schedule(
        enabled=True,
        days=parse_days(DEFAULT_DAYS),
        windows=parse_windows(DEFAULT_WINDOWS),
    )


def _default_sections() -> dict:
    return {
        "cesar": _default_cesar(),
        "watcher": _default_watcher(),
        "signature": SignatureConfig(),
        "notifications": NotificationConfig(),
        "selectors": Selectors.from_dict({}),
        "schedule": _default_schedule(),
        "updates": UpdatesConfig(),
    }


def default_config() -> Config:
    """Configuration proposee par l'assistant : reglages recommandes."""
    return Config(**_default_sections())


def _days_to_names(days: tuple[int, ...]) -> list[str]:
    ordered = sorted(DAY_NAMES.items(), key=lambda item: item[1])
    return [name for name, index in ordered if index in days]


def _attr_dict(obj, names: tuple[str, ...]) -> dict:
    return {name: getattr(obj, name) for name in names}


def _with_secret(data: dict, password=None, password_env=None) -> dict:
    if password:
        data["password"] = password
    elif password_env:
        data["password_env"] = password_env
    return data


def _cesar_to_dict(
    cesar: CesarConfig, password=None, password_env=None
) -> dict:
    data = {
        "base_url": cesar.base_url,
        "login_path": cesar.login_path,
        "dashboard_path": cesar.dashboard_path,
        "username": cesar.username,
        "keyring_service": cesar.keyring_service,
    }
    return _with_secret(data, password, password_env)


WATCHER_SCALARS = (
    "poll_interval",
    "dedupe_ttl",
    "confirm_timeout",
    "prompt_retry",
    "transport",
)
WATCHER_FLAGS = ("auto_sign", "auto_sign_delay", "headless", "visible_on_sign")


def _watcher_paths(watcher: WatcherConfig) -> dict:
    return {
        "profile_dir": str(watcher.profile_dir),
        "state_file": str(watcher.state_file),
        "http_cookies_file": str(watcher.http_cookies_file),
    }


def _watcher_to_dict(watcher: WatcherConfig) -> dict:
    data = {
        name: getattr(watcher, name)
        for name in WATCHER_SCALARS + WATCHER_FLAGS
    }
    data.update(_watcher_paths(watcher))
    if watcher.executable_path:
        data["executable_path"] = watcher.executable_path
    return data


def _signature_to_dict(signature: SignatureConfig) -> dict:
    return {
        "file": str(signature.file),
        "padding_ratio": signature.padding_ratio,
    }


def _notifications_to_dict(notifications: NotificationConfig) -> dict:
    return _attr_dict(notifications, ("app_name", "icon", "enabled"))


def _schedule_to_dict(schedule: Schedule) -> dict:
    return {
        "enabled": schedule.enabled,
        "days": _days_to_names(schedule.days),
        "windows": [str(window) for window in schedule.windows],
    }


def _selectors_to_dict(selectors: Selectors) -> dict:
    first = ("attendance_button", "signature_canvas", "signature_save")
    last = ("confirmation", "login_username", "login_password", "login_submit")
    return {key: list(getattr(selectors, key)) for key in first + last}


def _remaining_sections(config: Config) -> dict:
    return {
        "signature": _signature_to_dict(config.signature),
        "notifications": _notifications_to_dict(config.notifications),
        "schedule": _schedule_to_dict(config.schedule),
        "updates": _attr_dict(config.updates, ("enabled", "channel")),
        "analytics": _attr_dict(config.analytics, ("enabled", "endpoint")),
        "selectors": _selectors_to_dict(config.selectors),
    }


def config_to_dict(
    config: Config, *, password=None, password_env=None
) -> dict:
    sections = {
        "cesar": _cesar_to_dict(config.cesar, password, password_env),
        "watcher": _watcher_to_dict(config.watcher),
    }
    sections.update(_remaining_sections(config))
    return sections


RETRY_WARNING = "ecriture de la configuration retentee (%s/4) : %s"


def _config_payload(
    config: Config, *, password: str | None, password_env: str | None
) -> str:
    return tomli_w.dumps(
        config_to_dict(config, password=password, password_env=password_env)
    )


def _prepare_temp_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")


def _write_secure_temp(temporary: Path, payload: str) -> None:
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)


def _make_writable(target: Path) -> None:
    if not target.exists():
        return
    try:
        target.chmod(stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _try_replace(temporary: Path, target: Path) -> OSError | None:
    _make_writable(target)
    try:
        temporary.replace(target)
        return None
    except OSError as exc:
        return exc


def _retry_replace(
    temporary: Path, target: Path, attempts: int, delay: float
) -> OSError | None:
    last_error = None
    for attempt in range(attempts):
        last_error = _try_replace(temporary, target)
        if last_error is None:
            return None
        logger.warning(RETRY_WARNING, attempt + 1, last_error)
        time.sleep(delay * (attempt + 1))
    return last_error


def _replace_with_retries(
    temporary: Path, target: Path, attempts: int = 4, delay: float = 0.15
) -> Path:
    last_error = _retry_replace(temporary, target, attempts, delay)
    if last_error is not None:
        raise last_error
    return target


def _discard_temp(temporary: Path) -> None:
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass


def _write_config_atomically(target: Path, payload: str) -> Path:
    temporary = _prepare_temp_path(target)
    try:
        _write_secure_temp(temporary, payload)
        return _replace_with_retries(temporary, target)
    finally:
        _discard_temp(temporary)


def _prepare_config_target(path: str | Path) -> Path:
    target = expand_path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def save_config(
    path: str | Path,
    config: Config,
    *,
    password: str | None = None,
    password_env: str | None = None,
) -> Path:
    target = _prepare_config_target(path)
    payload = _config_payload(
        config, password=password, password_env=password_env
    )
    return _write_config_atomically(target, payload)


def _read_toml(config_path: Path) -> dict:
    if not config_path.is_file():
        raise ConfigError(
            f"fichier de configuration introuvable : {config_path}"
        )
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def _table(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] doit etre une table TOML")
    return value


def _http(value: str, name: str, key: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise ConfigError(
            f"[{name}] {key} doit commencer par http:// ou https://"
        )
    return value


def _int(table: dict, key: str, default: int) -> int:
    return int(table.get(key, default))


def _bool(table: dict, key: str, default: bool) -> bool:
    return bool(table.get(key, default))


def _path(table: dict, key: str, default: Path) -> Path:
    return expand_path(str(table.get(key, default)))


def _opt_str(table: dict, key: str) -> str | None:
    value = table.get(key)
    return str(value) if value else None


def _build_cesar(
    table: dict, base_url: str, username: str, password: str, service: str
) -> CesarConfig:
    login_path = str(table.get("login_path", "/connexion"))
    dashboard_path = str(table.get("dashboard_path", "/"))
    return CesarConfig(
        base_url, username, password, service, login_path, dashboard_path
    )


def _load_cesar(data: dict, *, require_password: bool) -> CesarConfig:
    table = _table(data, "cesar")
    username = _require(table, "username", "cesar")
    service = str(table.get("keyring_service", DEFAULT_SERVICE))
    raw_base = _require(table, "base_url", "cesar").rstrip("/")
    password = _resolve_password(table, username, service, require_password)
    base_url = _http(raw_base, "cesar", "base_url")
    return _build_cesar(table, base_url, username, password, service)


def _watcher_auto_config(table: dict, defaults: WatcherConfig) -> dict:
    return {
        "auto_sign": _bool(table, "auto_sign", defaults.auto_sign),
        "auto_sign_delay": _int(
            table, "auto_sign_delay", defaults.auto_sign_delay
        ),
    }


def _watcher_timing(table: dict, defaults: WatcherConfig) -> dict:
    data = {
        "poll_interval": _int(table, "poll_interval", defaults.poll_interval),
        "dedupe_ttl": _int(table, "dedupe_ttl", defaults.dedupe_ttl),
        "confirm_timeout": _int(
            table, "confirm_timeout", defaults.confirm_timeout
        ),
        "prompt_retry": _int(table, "prompt_retry", defaults.prompt_retry),
    }
    data.update(_watcher_auto_config(table, defaults))
    return data


def _watcher_path_config(table: dict, defaults: WatcherConfig) -> dict:
    return {
        "profile_dir": _path(table, "profile_dir", defaults.profile_dir),
        "state_file": _path(table, "state_file", defaults.state_file),
        "http_cookies_file": _path(
            table, "http_cookies_file", defaults.http_cookies_file
        ),
    }


def _watcher_transport(table: dict, defaults: WatcherConfig) -> str:
    raw = table.get("transport", defaults.transport)
    return str(raw).strip().lower()


def _watcher_flags(table: dict, defaults: WatcherConfig) -> dict:
    data = {
        "headless": _bool(table, "headless", defaults.headless),
        "visible_on_sign": _bool(
            table, "visible_on_sign", defaults.visible_on_sign
        ),
        "executable_path": _opt_str(table, "executable_path"),
        "transport": _watcher_transport(table, defaults),
    }
    data.update(_watcher_path_config(table, defaults))
    return data


def _load_watcher(data: dict) -> WatcherConfig:
    table = data.get("watcher", {})
    defaults = WatcherConfig()
    timing = _watcher_timing(table, defaults)
    flags = _watcher_flags(table, defaults)
    return WatcherConfig(**{**timing, **flags})


def _load_signature(data: dict) -> SignatureConfig:
    table = data.get("signature", {})
    defaults = SignatureConfig()
    return SignatureConfig(
        file=_path(table, "file", defaults.file),
        padding_ratio=float(
            table.get("padding_ratio", defaults.padding_ratio)
        ),
    )


def _load_notifications(data: dict) -> NotificationConfig:
    table = data.get("notifications", {})
    defaults = NotificationConfig()
    return NotificationConfig(
        app_name=str(table.get("app_name", defaults.app_name)),
        icon=str(table.get("icon", defaults.icon)),
        enabled=_bool(table, "enabled", defaults.enabled),
    )


def _load_selectors(data: dict) -> Selectors:
    return Selectors.from_dict(data.get("selectors", {}))


def _load_updates(data: dict) -> UpdatesConfig:
    table = data.get("updates", {})
    defaults = UpdatesConfig()
    enabled = _bool(table, "enabled", defaults.enabled)
    return UpdatesConfig(enabled=enabled, channel=parse_updates_channel(table))


def _load_analytics(data: dict) -> AnalyticsConfig:
    table = _table(data, "analytics")
    defaults = AnalyticsConfig()
    enabled = _bool(table, "enabled", defaults.enabled)
    endpoint = str(table.get("endpoint", defaults.endpoint))
    if enabled:
        _http(endpoint, "analytics", "endpoint")
    return AnalyticsConfig(enabled=enabled, endpoint=endpoint)


def _load_schedule(data: dict) -> Schedule:
    table = data.get("schedule", {})
    try:
        return Schedule(
            enabled=bool(table.get("enabled", False)),
            days=parse_days(table.get("days", DEFAULT_DAYS)),
            windows=parse_windows(table.get("windows", DEFAULT_WINDOWS)),
        )
    except ScheduleError as exc:
        raise ConfigError(f"[schedule] {exc}") from exc


def _validate_padding(signature: SignatureConfig) -> None:
    ratio = signature.padding_ratio
    if ratio < MIN_PADDING_RATIO or ratio > MAX_PADDING_RATIO:
        raise ConfigError(
            f"[signature] padding_ratio doit etre entre "
            f"{MIN_PADDING_RATIO} et {MAX_PADDING_RATIO}"
        )


def _validate_watcher(watcher: WatcherConfig) -> None:
    if watcher.transport not in {"browser", "http"}:
        raise ConfigError(
            "[watcher] transport doit valoir 'browser' ou 'http'"
        )
    if watcher.poll_interval < 10:
        raise ConfigError("[watcher] poll_interval doit etre >= 10 secondes")
    if watcher.confirm_timeout < 10:
        raise ConfigError("[watcher] confirm_timeout doit etre >= 10 secondes")
    if watcher.prompt_retry < 30:
        raise ConfigError("[watcher] prompt_retry doit etre >= 30 secondes")


def _validate_limits(
    watcher: WatcherConfig, signature: SignatureConfig
) -> None:
    _validate_watcher(watcher)
    _validate_padding(signature)


def _load_parts(data: dict, require_password: bool) -> dict:
    return {
        "cesar": _load_cesar(data, require_password=require_password),
        "watcher": _load_watcher(data),
        "signature": _load_signature(data),
        "notifications": _load_notifications(data),
        "selectors": _load_selectors(data),
        "updates": _load_updates(data),
        "analytics": _load_analytics(data),
    }


def save_updates_channel(path: str | Path, channel: str) -> Config:
    """Change le canal de mise a jour sans toucher aux secrets du fichier."""
    target = expand_path(str(path))
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    updates = data.setdefault("updates", {})
    if not isinstance(updates, dict):
        raise ConfigError("[updates] doit etre une table TOML")
    updates["channel"] = _validate_channel(_normalize_channel(channel))
    _write_config_atomically(target, tomli_w.dumps(data))
    return load_config(target, require_password=False)


def load_config(path: str | Path, *, require_password: bool = True) -> Config:
    data = _read_toml(Path(path))
    parts = _load_parts(data, require_password)
    parts["schedule"] = _load_schedule(data)
    _validate_limits(parts["watcher"], parts["signature"])
    return Config(**parts)
