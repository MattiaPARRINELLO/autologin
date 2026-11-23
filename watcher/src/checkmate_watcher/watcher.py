"""Boucle de surveillance et orchestration des actions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import BUILD, __version__, analytics
from .cesar import (
    AttendanceSignal,
    CesarError,
    CesarSession,
    SignError,
    is_success_confirmation,
)
from .config import Config
from .errors import describe_error
from .notifications import Notifier
from .paths import default_config_path
from .signature import load_signature
from .state import StateStore
from .status_server import StatusSession, start_status_server, stop_status_server
from .tray import TrayController
from .updates import check_for_update

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 3

MAX_WAIT_CHUNK = 300.0
HEARTBEAT_SECONDS = 300.0


class StopRequested(Exception):
    """Demande d'arret depuis le tableau de bord ou l'icone."""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _record_error(state: StateStore, exc: BaseException) -> None:
    """Garde la cause de l'erreur pour l'afficher dans le tableau de bord."""
    kind, message = describe_error(exc)
    state.set_meta("last_error_at", _now_iso())
    state.set_meta("last_error_kind", kind)
    state.set_meta("last_error_message", message)


SIGN = "sign"
ABSENT = "absent"
NO_ANSWER = "no_answer"
DRY_RUN = "dry_run"


def _notifier(config: Config) -> Notifier:
    return Notifier.from_config(config)


async def _send(
    config: Config, title: str, message: str, *, icon: str, urgency: str = "critical"
) -> bool:
    if not config.notifications.enabled:
        logger.debug("notification desactivee : %s", title)
        return False
    notifier = _notifier(config)
    return await asyncio.to_thread(notifier.send, title, message, urgency=urgency)


@dataclass(frozen=True)
class Pause:
    """Raison de suspendre la surveillance jusqu'a la prochaine ouverture."""

    reason: str
    resume: datetime
    window_key: str | None


def _pause_reason(schedule, state, now: datetime) -> Pause | None:
    situation = schedule.situation(now, state.window_done)
    if situation.reason not in {"outside", "signed"}:
        return None
    resume = now + timedelta(seconds=schedule.seconds_until_next(now))
    label = "hors plage" if situation.reason == "outside" else "creneau deja signe"
    return Pause(label, resume, situation.key)


async def _wait_for_new_window(
    schedule, current_key: str | None, stop_event=None
) -> None:
    """Attend un changement de creneau, par tranches courtes.

    Les tranches evitent de rater la reprise apres une mise en veille et
    permettent de repondre vite a une demande d'arret.
    """
    while True:
        if stop_event is not None and stop_event.is_set():
            raise StopRequested
        now = datetime.now()
        if current_key is None:
            if schedule.active_window(now) is not None:
                return
        elif schedule.window_key(now) != current_key:
            return

        next_start = schedule.next_start(now)
        remaining = (next_start - now).total_seconds() if next_start else 3600
        await asyncio.sleep(min(max(remaining, 0.5), 5.0))


async def _check_update(config: Config, state: StateStore) -> None:
    if not config.updates.enabled:
        return
    try:
        release = await asyncio.wait_for(
            asyncio.to_thread(
                check_for_update,
                __version__,
                channel=config.updates.channel,
            ),
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("verification de mise a jour impossible : %s", exc)
        return
    if release is None:
        return
    if state.get_meta("update_notified") == release.tag:
        return
    logger.info("mise a jour disponible : %s", release.tag)
    await _send(
        config,
        "Mise a jour disponible",
        f"CheckMate {release.version_text} est disponible.\n{release.url}",
        icon="dialog-information",
        urgency="normal",
    )
    state.set_meta("update_notified", release.tag)


async def sign_with_visibility(
    config: Config,
    session: CesarSession,
    points: list,
) -> str:
    """Signe en mode invisible, ou en ouvrant une fenetre uniquement pour signer."""
    if not config.watcher.visible_on_sign:
        return await session.sign(points)

    logger.info("ouverture du navigateur visible pour la signature")
    await session.switch_headless(False)
    try:
        signal = await session.check()
        if signal is None:
            raise SignError(
                "emargement introuvable a l'ouverture du navigateur visible"
            )
        confirmation = await session.sign(points)
        # Laisser le temps de voir la confirmation avant de refermer.
        await asyncio.sleep(2)
        return confirmation
    finally:
        await session.switch_headless(True)


async def handle_signal(
    config: Config,
    signal: AttendanceSignal,
    *,
    dry_run: bool,
    auto: bool,
) -> str:
    """Notifie et renvoie la decision : sign, absent, no_answer ou dry_run."""
    message = (
        f"{signal.label}\n\n"
        "Une fenetre de confirmation s'ouvre. Choisis 'Je suis present' "
        "pour signer automatiquement."
    )

    if dry_run:
        logger.info("[dry-run] emargement detecte : %s", signal.label)
        return DRY_RUN

    await _send(config, "Emargement ouvert", message, icon=config.notifications.icon)

    if auto:
        delay = max(0, config.watcher.auto_sign_delay)
        logger.info("signature automatique dans %ss", delay)
        await _send(
            config,
            "Signature automatique",
            f"{signal.label}\nSignature dans {delay}s.",
            icon=config.notifications.icon,
            urgency="normal",
        )
        if delay:
            await asyncio.sleep(delay)
        return SIGN

    if not config.notifications.enabled:
        logger.info("confirmations desactivees, aucune signature envoyee")
        return NO_ANSWER

    notifier = _notifier(config)
    answer = await asyncio.to_thread(
        notifier.ask,
        message,
        timeout=config.watcher.confirm_timeout,
        title=config.notifications.app_name,
    )
    if answer is True:
        logger.info("utilisateur present : signature demandee")
        return SIGN
    if answer is False:
        logger.info("utilisateur absent : aucune signature")
        await _send(
            config,
            "Emargement ignore",
            "Tu as indique etre absent. Aucune signature envoyee.",
            icon=config.notifications.icon,
            urgency="normal",
        )
        return ABSENT

    logger.info("aucune reponse a la confirmation, nouvelle tentative plus tard")
    await _send(
        config,
        "Emargement en attente",
        "Pas de reponse. Une nouvelle demande sera faite dans quelques minutes.",
        icon=config.notifications.icon,
        urgency="normal",
    )
    return NO_ANSWER


async def run_loop(
    config: Config,
    *,
    once: bool = False,
    dry_run: bool = False,
    auto_override: bool | None = None,
    config_path: Path | None = None,
) -> int:
    auto = config.watcher.auto_sign if auto_override is None else auto_override
    config_path = (config_path or default_config_path()).expanduser()

    try:
        points = load_signature(config.signature.file)
    except Exception as exc:  # noqa: BLE001
        if not dry_run:
            logger.error("signature indisponible : %s", exc)
            logger.error("lance 'checkmate-watcher capture' pour en creer une")
            return 2
        logger.warning("signature indisponible (%s), dry-run sans signature", exc)
        points = []

    started_at = datetime.now()
    state = StateStore(config.watcher.state_file, ttl=config.watcher.dedupe_ttl)
    state.increment("stats.starts")
    if not dry_run:
        analytics.record_startup(config, state)
    logger.info("CheckMate %s (build %s)", __version__, BUILD)

    status_session: StatusSession | None = None
    status_server = None
    tray: TrayController | None = None
    if not once:
        status_session = StatusSession(config, config_path, state, started_at)
        status_server = start_status_server(status_session)
        tray = TrayController(status_session)
        tray.start()
    stop_event = status_session.stop_event if status_session else None

    try:
        await _check_update(config, state)
        session = CesarSession(config)
        poll_headless = (
            True if config.watcher.visible_on_sign else config.watcher.headless
        )
        schedule = config.schedule

        pause = _pause_reason(schedule, state, datetime.now())
        if pause is not None:
            if once:
                logger.info(
                    "%s, prochaine ouverture %s",
                    pause.reason,
                    pause.resume.strftime("%d/%m %H:%M"),
                )
                return 0
            logger.info(
                "%s (%s), reprise vers %s",
                pause.reason,
                schedule.describe(),
                pause.resume.strftime("%d/%m %H:%M"),
            )
            await _wait_for_new_window(schedule, pause.window_key, stop_event)

        if stop_event is not None and stop_event.is_set():
            return 0
        await session.open(headless=poll_headless)

        consecutive_errors = 0
        prompt_cooldowns: dict[str, float] = {}
        window_key: str | None = None
        last_window_key: str | None = None
        next_heartbeat = asyncio.get_running_loop().time() + HEARTBEAT_SECONDS
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    return 0

                now = datetime.now()
                pause = _pause_reason(schedule, state, now)
                if pause is not None:
                    if once:
                        logger.info(
                            "%s, prochaine ouverture %s",
                            pause.reason,
                            pause.resume.strftime("%d/%m %H:%M"),
                        )
                        return 0
                    logger.info(
                        "%s, pause jusqu'a %s",
                        pause.reason,
                        pause.resume.strftime("%d/%m %H:%M"),
                    )
                    await session.close()
                    await _wait_for_new_window(schedule, pause.window_key, stop_event)
                    await session.open(headless=poll_headless)
                    continue

                window_key = schedule.window_key(now)
                if window_key != last_window_key:
                    window = schedule.active_window(now)
                    if window is not None:
                        logger.info(
                            "surveillance active sur le creneau %s (toutes les %ss)",
                            window,
                            config.watcher.poll_interval,
                        )
                    last_window_key = window_key

                try:
                    signal = await session.check()
                    consecutive_errors = 0

                    if signal is None:
                        logger.debug("rien a signer")
                        if asyncio.get_running_loop().time() >= next_heartbeat:
                            logger.info("surveillance active, aucun emargement detecte")
                            next_heartbeat = (
                                asyncio.get_running_loop().time() + HEARTBEAT_SECONDS
                            )
                    elif state.seen(signal.key):
                        logger.debug("emargement deja traite : %s", signal.key)
                    elif (
                        prompt_cooldowns.get(signal.key, 0)
                        > asyncio.get_running_loop().time()
                    ):
                        logger.debug("nouvelle demande en attente pour %s", signal.key)
                    else:
                        state.increment("stats.detections")
                        state.set_meta("last_detection_at", _now_iso())
                        decision = await handle_signal(
                            config,
                            signal,
                            dry_run=dry_run,
                            auto=auto,
                        )
                        if decision == DRY_RUN:
                            pass
                        elif decision == ABSENT:
                            state.mark(signal.key)
                        elif decision == NO_ANSWER:
                            prompt_cooldowns[signal.key] = (
                                asyncio.get_running_loop().time()
                                + config.watcher.prompt_retry
                            )
                        else:
                            try:
                                confirmation = await sign_with_visibility(
                                    config, session, points
                                )
                            except CesarError as exc:
                                logger.error("echec de la signature : %s", exc)
                                state.increment("stats.errors")
                                _record_error(state, exc)
                                prompt_cooldowns[signal.key] = (
                                    asyncio.get_running_loop().time()
                                    + config.watcher.prompt_retry
                                )
                                await _send(
                                    config,
                                    "Echec du pointage",
                                    f"{signal.label}\n{exc}",
                                    icon="dialog-error",
                                )
                            else:
                                state.mark(signal.key)
                                state.increment("stats.signed")
                                analytics.record(config, "signature")
                                state.set_meta("last_signed_at", _now_iso())
                                if window_key:
                                    state.mark_window(window_key)
                                if is_success_confirmation(confirmation):
                                    logger.info("presence signee : %s", confirmation)
                                    await _send(
                                        config,
                                        "Presence pointee",
                                        "Emargement signe avec succes.",
                                        icon="dialog-information",
                                    )
                                else:
                                    logger.warning(
                                        "confirmation inattendue : %s", confirmation
                                    )
                                    await _send(
                                        config,
                                        "Pointage a verifier",
                                        f"Reponse du site : {confirmation}",
                                        icon="dialog-warning",
                                    )

                except StopRequested:
                    return 0
                except Exception as exc:  # noqa: BLE001
                    consecutive_errors += 1
                    state.increment("stats.errors")
                    _record_error(state, exc)
                    logger.error("erreur pendant la surveillance : %s", exc)
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.warning(
                            "redemarrage du navigateur apres %s erreurs",
                            consecutive_errors,
                        )
                        try:
                            await session.restart()
                            consecutive_errors = 0
                        except Exception as restart_exc:  # noqa: BLE001
                            logger.error("redemarrage impossible : %s", restart_exc)
                            return 1

                if once:
                    return 0

                await asyncio.sleep(config.watcher.poll_interval)
        finally:
            await session.close()
    except StopRequested:
        return 0
    finally:
        if tray is not None:
            tray.stop()
        if status_server is not None:
            stop_status_server(status_server)
