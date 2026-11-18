"""Boucle de surveillance et orchestration des actions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from . import notify
from .cesar import (
    AttendanceSignal,
    CesarError,
    CesarSession,
    SignError,
    is_success_confirmation,
)
from .config import Config
from .signature import load_signature
from .state import StateStore

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 3

MAX_WAIT_CHUNK = 300.0

SIGN = "sign"
ABSENT = "absent"
NO_ANSWER = "no_answer"
DRY_RUN = "dry_run"


async def _send(
    config: Config, title: str, message: str, *, icon: str, urgency: str = "critical"
) -> bool:
    if not config.notifications.enabled:
        logger.debug("notification desactivee : %s", title)
        return False
    return await asyncio.to_thread(
        notify.send,
        title,
        message,
        app_name=config.notifications.app_name,
        icon=icon,
        urgency=urgency,
    )


async def _wait_for_new_window(schedule, current_key: str | None) -> None:
    """Attend un changement de creneau, par tranches de 5 minutes.

    Les tranches evitent de rater la reprise apres une mise en veille : un
    asyncio.sleep long ne tient pas compte du temps de suspension.
    """
    while True:
        now = datetime.now()
        if current_key is None:
            if schedule.active_window(now) is not None:
                return
        elif schedule.window_key(now) != current_key:
            return
        wait = min(schedule.seconds_until_next(now), MAX_WAIT_CHUNK)
        await asyncio.sleep(wait)


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

    answer = await asyncio.to_thread(
        notify.ask,
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
) -> int:
    auto = config.watcher.auto_sign if auto_override is None else auto_override

    try:
        points = load_signature(config.signature.file)
    except Exception as exc:  # noqa: BLE001
        if not dry_run:
            logger.error("signature indisponible : %s", exc)
            logger.error("lance 'checkmate-watcher capture' pour en creer une")
            return 2
        logger.warning("signature indisponible (%s), dry-run sans signature", exc)
        points = []

    state = StateStore(config.watcher.state_file, ttl=config.watcher.dedupe_ttl)
    session = CesarSession(config)
    poll_headless = True if config.watcher.visible_on_sign else config.watcher.headless
    schedule = config.schedule

    if schedule.enabled:
        now = datetime.now()
        if schedule.active_window(now) is None:
            wait = schedule.seconds_until_next(now)
            resume = now + timedelta(seconds=wait)
            if once:
                logger.info(
                    "hors plage de surveillance, prochaine ouverture %s",
                    resume.strftime("%d/%m %H:%M"),
                )
                return 0
            logger.info(
                "hors plage (%s), reprise vers %s",
                schedule.describe(),
                resume.strftime("%d/%m %H:%M"),
            )
            await _wait_for_new_window(schedule, None)
            now = datetime.now()

        current_key = schedule.window_key(now)
        if current_key and state.window_done(current_key):
            wait = schedule.seconds_until_next(now)
            resume = now + timedelta(seconds=wait)
            if once:
                logger.info(
                    "creneau deja signe, prochaine ouverture %s",
                    resume.strftime("%d/%m %H:%M"),
                )
                return 0
            logger.info(
                "deja signe sur ce creneau, pause jusqu'a %s",
                resume.strftime("%d/%m %H:%M"),
            )
            await _wait_for_new_window(schedule, current_key)

    await session.open(headless=poll_headless)

    consecutive_errors = 0
    prompt_cooldowns: dict[str, float] = {}
    window_key: str | None = None
    try:
        while True:
            if schedule.enabled:
                now = datetime.now()
                if schedule.active_window(now) is None:
                    wait = schedule.seconds_until_next(now)
                    resume = now + timedelta(seconds=wait)
                    if once:
                        logger.info(
                            "hors plage, prochaine ouverture %s",
                            resume.strftime("%d/%m %H:%M"),
                        )
                        return 0
                    logger.info(
                        "fin de plage, pause jusqu'a %s",
                        resume.strftime("%d/%m %H:%M"),
                    )
                    await session.close()
                    await _wait_for_new_window(schedule, None)
                    await session.open(headless=poll_headless)
                    continue

                window_key = schedule.window_key(now)
                if window_key and state.window_done(window_key):
                    wait = schedule.seconds_until_next(now)
                    resume = now + timedelta(seconds=wait)
                    if once:
                        logger.info(
                            "creneau deja signe, prochaine ouverture %s",
                            resume.strftime("%d/%m %H:%M"),
                        )
                        return 0
                    logger.info(
                        "deja signe sur ce creneau, pause jusqu'a %s",
                        resume.strftime("%d/%m %H:%M"),
                    )
                    await session.close()
                    await _wait_for_new_window(schedule, window_key)
                    await session.open(headless=poll_headless)
                    continue

            try:
                signal = await session.check()
                consecutive_errors = 0

                if signal is None:
                    logger.debug("rien a signer")
                elif state.seen(signal.key):
                    logger.debug("emargement deja traite : %s", signal.key)
                elif (
                    prompt_cooldowns.get(signal.key, 0)
                    > asyncio.get_running_loop().time()
                ):
                    logger.debug("nouvelle demande en attente pour %s", signal.key)
                else:
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

            except Exception as exc:  # noqa: BLE001
                consecutive_errors += 1
                logger.error("erreur pendant la surveillance : %s", exc)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "redemarrage du navigateur apres %s erreurs", consecutive_errors
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
