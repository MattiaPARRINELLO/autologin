"""Boucle de surveillance et orchestration des actions."""

from __future__ import annotations

import asyncio
import logging

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


async def _send(
    config: Config, title: str, message: str, *, icon: str, urgency: str = "critical"
) -> bool:
    return await asyncio.to_thread(
        notify.send,
        title,
        message,
        app_name=config.notifications.app_name,
        icon=icon,
        urgency=urgency,
    )


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
) -> bool:
    """Notifie et, si l'utilisateur accepte, signe. Renvoie True si signe."""
    message = (
        f"{signal.label}\n\n"
        "Une fenetre de confirmation s'ouvre. Choisis 'Je suis present' "
        "pour signer automatiquement."
    )

    if dry_run:
        logger.info("[dry-run] emargement detecte : %s", signal.label)
        return False

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
        return True

    if not config.notifications.enabled:
        logger.info("confirmations desactivees, signature refusee")
        return False

    answer = await asyncio.to_thread(
        notify.ask,
        message,
        timeout=config.watcher.confirm_timeout,
        title=config.notifications.app_name,
    )
    if answer is True:
        logger.info("utilisateur present : signature demandee")
        return True
    if answer is False:
        logger.info("utilisateur absent : aucune signature")
        await _send(
            config,
            "Emargement ignore",
            "Tu as indique etre absent. Aucune signature envoyee.",
            icon=config.notifications.icon,
            urgency="normal",
        )
    else:
        logger.info("aucune reponse a la confirmation")
        await _send(
            config,
            "Emargement en attente",
            "Pas de reponse. Aucune signature envoyee.",
            icon=config.notifications.icon,
            urgency="normal",
        )
    return False


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
    await session.open(
        headless=True if config.watcher.visible_on_sign else config.watcher.headless
    )

    consecutive_errors = 0
    try:
        while True:
            try:
                signal = await session.check()
                consecutive_errors = 0

                if signal is None:
                    logger.debug("rien a signer")
                elif state.seen(signal.key):
                    logger.debug("emargement deja traite : %s", signal.key)
                else:
                    accepted = await handle_signal(
                        config,
                        signal,
                        dry_run=dry_run,
                        auto=auto,
                    )
                    if dry_run:
                        pass
                    elif not accepted:
                        state.mark(signal.key)
                    else:
                        try:
                            confirmation = await sign_with_visibility(
                                config, session, points
                            )
                        except CesarError as exc:
                            logger.error("echec de la signature : %s", exc)
                            await _send(
                                config,
                                "Echec du pointage",
                                f"{signal.label}\n{exc}",
                                icon="dialog-error",
                            )
                        else:
                            state.mark(signal.key)
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
