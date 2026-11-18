"""Pilotage de CESAR Emineo avec Playwright."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .browser import resolve_executable
from .config import Config
from .signature import FittedPoint, Point, fit_points

logger = logging.getLogger(__name__)

SUCCESS_KEYWORDS = ("presence", "prise en compte", "present", "signe", "enregistr")


class CesarError(Exception):
    """Erreur generale de pilotage du site."""


class LoginError(CesarError):
    """Connexion impossible."""


class SignError(CesarError):
    """Signature impossible."""


@dataclass(frozen=True)
class AttendanceSignal:
    key: str
    label: str


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).lower()


def is_success_confirmation(text: str) -> bool:
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in SUCCESS_KEYWORDS)


def signal_key(payload: dict[str, str]) -> str:
    """Cle stable pour dedupliquer un emargement entre deux rafraichissements."""
    action = (payload.get("action") or "").strip()
    row = re.sub(r"\s+", " ", payload.get("row") or "").strip()
    label = re.sub(r"\s+", " ", payload.get("label") or "").strip()
    basis = "|".join(
        [
            date.today().isoformat(),
            action or label,
            row,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


class CesarSession:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.selectors = config.selectors
        self.page = None
        self._playwright = None
        self._context = None
        self.headless = config.watcher.headless

    async def open(self, headless: bool | None = None) -> None:
        from playwright.async_api import async_playwright

        self.headless = self.config.watcher.headless if headless is None else headless
        self.config.watcher.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        executable = resolve_executable(self._playwright.chromium, self.config)
        options = {"executable_path": executable} if executable else {}
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.watcher.profile_dir),
            headless=self.headless,
            viewport={"width": 1366, "height": 900},
            args=["--no-first-run", "--no-default-browser-check"],
            **options,
        )
        self._context.set_default_timeout(20000)
        pages = self._context.pages
        self.page = pages[0] if pages else await self._context.new_page()
        mode = "invisible" if self.headless else "visible"
        logger.info(
            "navigateur demarre en mode %s (profil %s)",
            mode,
            self.config.watcher.profile_dir,
        )

    async def switch_headless(self, headless: bool) -> None:
        """Relance le navigateur dans le mode demande.

        Le profil persistant conserve la session, donc aucunlogin n'est necessaire.
        """
        if self._context is not None and self.headless == headless:
            return
        await self.close()
        await self.open(headless=headless)

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                logger.debug("fermeture du contexte impossible", exc_info=True)
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                logger.debug("arret de playwright impossible", exc_info=True)
            self._playwright = None

    async def restart(self) -> None:
        await self.close()
        await asyncio.sleep(2)
        await self.open()

    async def _first_visible(self, selectors: tuple[str, ...]):
        if self.page is None:
            return None
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible():
                    return locator
            except Exception:
                logger.debug("selecteur %s non exploitable", selector, exc_info=True)
                continue
        return None

    async def _goto_dashboard(self) -> None:
        if self.page is None:
            raise CesarError("navigateur non demarre")
        logger.debug("rafraichissement du tableau de bord")
        await self.page.goto(
            self.config.cesar.dashboard_url,
            wait_until="domcontentloaded",
            timeout=45000,
        )
        # Le calendrier et le bouton sont rendus en JS apres le chargement.
        await self.page.wait_for_timeout(2500)

    async def _ensure_logged_in(self) -> None:
        if self.page is None:
            raise CesarError("navigateur non demarre")
        if self.config.cesar.login_path in self.page.url:
            await self._login()
            return

        username = await self._first_visible(self.selectors.login_username)
        password = await self._first_visible(self.selectors.login_password)
        if username is not None and password is not None:
            await self._login()

    async def _login(self) -> None:
        if self.page is None:
            raise LoginError("navigateur non demarre")
        logger.info("connexion a CESAR")
        try:
            await self.page.goto(
                self.config.cesar.login_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            username = await self._first_visible(self.selectors.login_username)
            password = await self._first_visible(self.selectors.login_password)
            if username is None or password is None:
                raise LoginError("champs de connexion introuvables")

            await username.fill(self.config.cesar.username)
            await password.fill(self.config.cesar.password)

            submit = await self._first_visible(self.selectors.login_submit)
            if submit is None:
                raise LoginError("bouton de connexion introuvable")
            await submit.click()

            await self.page.wait_for_url(
                lambda url: self.config.cesar.login_path not in url,
                timeout=45000,
            )
            await self.page.wait_for_timeout(2500)
        except LoginError:
            raise
        except Exception as exc:
            raise LoginError(f"connexion echouee : {exc}") from exc

        logger.info("connexion reussie")

    async def check(self) -> AttendanceSignal | None:
        """Rafraichit le tableau de bord et cherche le bouton d'emargement."""
        await self._goto_dashboard()
        await self._ensure_logged_in()

        button = await self._first_visible(self.selectors.attendance_button)
        if button is None:
            logger.debug("aucun bouton d'emargement visible apres rafraichissement")
            return None

        try:
            payload = await button.evaluate(
                """(el) => {
                    const attrs = {};
                    for (const attr of el.attributes) attrs[attr.name] = attr.value;
                    const row = el.closest('tr, li, .card, [data-course-id], [data-session-id]');
                    return {
                        action: attrs['data-live-action-param'] || attrs['data-course-id'] || attrs['data-session-id'] || '',
                        row: row ? (row.innerText || '').slice(0, 300) : '',
                        label: (el.innerText || '').trim(),
                    };
                }"""
            )
        except Exception:  # noqa: BLE001
            payload = {"action": "", "row": "", "label": ""}

        label = (payload.get("label") or "").strip() or "Emargement ouvert"
        key = signal_key(payload)
        logger.info("bouton d'emargement detecte : %s", label)
        return AttendanceSignal(key=key, label=label)

    async def sign(self, points: list[Point]) -> str:
        """Clique sur le bouton, rejoue la signature et valide.

        Renvoie le texte de confirmation affiche par le site.
        """
        if self.page is None:
            raise SignError("navigateur non demarre")

        button = await self._first_visible(self.selectors.attendance_button)
        if button is None:
            raise SignError("bouton d'emargement introuvable")

        await button.click()
        canvas = await self._wait_for_selector(self.selectors.signature_canvas, 20000)
        await self.page.wait_for_timeout(800)

        box = await canvas.bounding_box()
        if box is None or box["width"] <= 0 or box["height"] <= 0:
            raise SignError("canvas de signature sans dimensions")

        fitted = fit_points(
            points,
            box["width"],
            box["height"],
            self.config.signature.padding_ratio,
        )
        await self._draw(box, fitted)
        await self.page.wait_for_timeout(500)

        previous = await self._confirmation_text()
        confirm_button = await self._wait_for_selector(
            self.selectors.signature_save, 15000
        )
        await confirm_button.click()

        confirmation = await self._wait_for_confirmation(previous, 15000)
        if confirmation is None:
            raise SignError("aucune confirmation affichee apres la signature")
        logger.info("confirmation du site : %s", confirmation)
        return confirmation

    async def _draw(self, box: dict, points: list[FittedPoint]) -> None:
        if self.page is None:
            raise SignError("navigateur non demarre")
        first = points[0]
        await self.page.mouse.move(box["x"] + first.x, box["y"] + first.y)
        await self.page.mouse.down()
        for point in points[1:]:
            await self.page.mouse.move(box["x"] + point.x, box["y"] + point.y, steps=2)
            await asyncio.sleep(0.008)
        last = points[-1]
        await self.page.mouse.move(box["x"] + last.x, box["y"] + last.y)
        await self.page.mouse.up()

    async def _wait_for_selector(self, selectors: tuple[str, ...], timeout_ms: int):
        if self.page is None:
            raise SignError("navigateur non demarre")
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            locator = await self._first_visible(selectors)
            if locator is not None:
                return locator
            await self.page.wait_for_timeout(250)
        raise SignError(
            f"element introuvable apres {timeout_ms}ms : {' | '.join(selectors)}"
        )

    async def _confirmation_text(self) -> str:
        if self.page is None:
            return ""
        locator = await self._first_visible(self.selectors.confirmation)
        if locator is None:
            return ""
        try:
            return (await locator.inner_text()).strip()
        except Exception:  # noqa: BLE001
            return ""

    async def _wait_for_confirmation(
        self, previous: str, timeout_ms: int
    ) -> str | None:
        if self.page is None:
            return None
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            await self.page.wait_for_timeout(300)
            current = await self._confirmation_text()
            if current and current != previous:
                return current
        return None
