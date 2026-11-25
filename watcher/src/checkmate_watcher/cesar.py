"""Pilotage de CESAR Emineo avec Playwright."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date

from .browser import resolve_launch_options
from .config import Config
from .signature import FittedPoint, Point, fit_points
from .signature_diagnostics import SignatureDiagnostics, diagnostics_directory

logger = logging.getLogger(__name__)

SUCCESS_KEYWORDS = ("presence", "prise en compte", "present", "signe", "enregistr")

READY_SELECTORS = (
    ".toastui-calendar-day-view",
    "div.toastui-calendar-layout",
)

CALENDAR_IDENTITY_JS = """
() => {
    const calendar = document.querySelector(
        '[data-tui-calendar-event-lesson-schedules-value]'
    );
    if (!calendar) return {};
    try {
        const student = JSON.parse(calendar.getAttribute(
            'data-tui-calendar-student-registration-value'
        ) || '{}');
        const courses = JSON.parse(calendar.getAttribute(
            'data-tui-calendar-event-lesson-schedules-value'
        ) || '[]');
        const maxMinutes = Number(calendar.getAttribute(
            'data-tui-calendar-max-time-attendance-value'
        ));
        const serverNow = Number(calendar.getAttribute(
            'data-tui-calendar-time-server-value'
        ));
        const find = (node, course) => {
            if (Array.isArray(node)) {
                for (const item of node) {
                    const found = find(item, course);
                    if (found) return found;
                }
                return null;
            }
            if (!node || typeof node !== 'object') return null;
            if (Array.isArray(node.attendanceSheetLines)) {
                for (const line of node.attendanceSheetLines) {
                    const registration = line.planningGroupSubscription
                        ?.studentRegistration;
                    const signed = line.signature?.signed === true
                        || line.attendanceWithoutSignature === true;
                    const secondsLeft = Math.round((
                        line.createdAt + maxMinutes * 60000 - serverNow * 1000
                    ) / 1000);
                    if (registration?.uuid === student.uuid
                        && line.signingOff === true && !signed
                        && secondsLeft > 0) {
                        return {
                            course_uuid: course?.uuid || '',
                            line_uuid: line.uuid || '',
                        };
                    }
                }
            }
            for (const value of Object.values(node)) {
                const found = find(value, course);
                if (found) return found;
            }
            return null;
        };
        for (const course of courses) {
            const found = find(course, course);
            if (found) return found;
        }
    } catch (error) {
        return {};
    }
    return {};
}
"""

# En dessous de ce ratio sur un des deux axes, le trace n'a pas la forme d'une
# signature, point (clic sans mouvement) ou ligne (canvas mesure pendant une
# animation, mouvements ignores par la librairie du site).
MIN_INK_RATIO = 0.05


def draw_coordinates(fitted: list[FittedPoint]) -> list[list[float]]:
    return [[round(point.x, 2), round(point.y, 2)] for point in fitted]


INK_SNAPSHOT_JS = """
(canvas) => {
  const context = canvas.getContext('2d');
  if (!context) return false;
  const width = canvas.width;
  const height = canvas.height;
  if (!width || !height) return false;
  try {
    const data = context.getImageData(0, 0, width, height).data;
    window.__checkmateInk = { data: new Uint8ClampedArray(data), width, height };
    return true;
  } catch (error) {
    return false;
  }
}
"""

INK_DIFF_JS = """
(canvas) => {
  const snapshot = window.__checkmateInk;
  const context = canvas.getContext('2d');
  if (!snapshot || !context) return null;
  if (canvas.width !== snapshot.width || canvas.height !== snapshot.height) return null;
  let data;
  try {
    data = context.getImageData(0, 0, snapshot.width, snapshot.height).data;
  } catch (error) {
    return null;
  }
  let minX = snapshot.width;
  let minY = snapshot.height;
  let maxX = -1;
  let maxY = -1;
  let count = 0;
  const step = 2;
  for (let y = 0; y < snapshot.height; y += step) {
    for (let x = 0; x < snapshot.width; x += step) {
      const index = (y * snapshot.width + x) * 4;
      if (
        data[index] !== snapshot.data[index] ||
        data[index + 1] !== snapshot.data[index + 1] ||
        data[index + 2] !== snapshot.data[index + 2] ||
        data[index + 3] !== snapshot.data[index + 3]
      ) {
        count += 1;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  return {
    count,
    minX,
    minY,
    maxX,
    maxY,
    width: snapshot.width,
    height: snapshot.height,
  };
}
"""

CANVAS_HITTABLE_JS = """
(canvas) => {
  const rect = canvas.getBoundingClientRect();
  const hit = document.elementFromPoint(
    rect.left + rect.width / 2,
    rect.top + rect.height / 2
  );
  return hit !== null && (hit === canvas || canvas.contains(hit));
}
"""

EVENT_DRAW_JS = """
async (canvas, coordinates) => {
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const rect = canvas.getBoundingClientRect();
  const withOffsets = (event, x, y) => {
    const values = {
      offsetX: x,
      offsetY: y,
      layerX: x,
      layerY: y,
      pageX: window.scrollX + rect.left + x,
      pageY: window.scrollY + rect.top + y,
      x: rect.left + x,
      y: rect.top + y,
    };
    for (const [key, value] of Object.entries(values)) {
      try {
        Object.defineProperty(event, key, { configurable: true, get: () => value });
      } catch (error) {
        // Certaines implementations verrouillent deja ces proprietes.
      }
    }
    return event;
  };
  const fire = (kind, x, y, buttons) => {
    const clientX = rect.left + x;
    const clientY = rect.top + y;
    const options = {
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX,
      clientY,
      screenX: window.screenX + clientX,
      screenY: window.screenY + clientY,
      button: 0,
      buttons,
    };
    const names = { down: 'mousedown', move: 'mousemove', up: 'mouseup' };
    canvas.dispatchEvent(withOffsets(new MouseEvent(names[kind], options), x, y));
    try {
      canvas.dispatchEvent(
        withOffsets(
          new PointerEvent('pointer' + kind, {
            ...options,
            pointerId: 1,
            pointerType: 'mouse',
            isPrimary: true,
            pressure: buttons ? 0.5 : 0,
          }),
          x,
          y
        )
      );
    } catch (error) {
      // PointerEvent non supporte.
    }
  };

  const first = coordinates[0];
  fire('down', first[0], first[1], 1);
  for (let index = 1; index < coordinates.length; index += 1) {
    await delay(8);
    fire('move', coordinates[index][0], coordinates[index][1], 1);
  }
  await delay(8);
  const last = coordinates[coordinates.length - 1];
  fire('up', last[0], last[1], 0);
  return true;
}
"""


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


def _signal_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ink_ratio(ink: dict, low: str, high: str, size: str) -> float:
    return (ink.get(high, -1) - ink.get(low, 0)) / max(1, ink.get(size, 1))


def signal_key(payload: dict[str, str]) -> str:
    """Cle stable pour dedupliquer un emargement entre deux rafraichissements."""
    course_uuid = _signal_text(payload.get("course_uuid"))
    line_uuid = _signal_text(payload.get("line_uuid"))
    if course_uuid and line_uuid:
        basis = f"{course_uuid}|{line_uuid}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    action = _signal_text(payload.get("action"))
    row = _signal_text(payload.get("row"))
    label = _signal_text(payload.get("label"))
    basis = "|".join([date.today().isoformat(), action or label, row])
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
        options = resolve_launch_options(
            self._playwright.chromium,
            self.config.watcher.executable_path,
        ).as_kwargs()
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
        headless = self.headless
        await self.close()
        await asyncio.sleep(2)
        await self.open(headless=headless)

    async def _wait_for_ready(self, timeout_ms: int = 6000) -> None:
        """Attend le premier element qui indique que la page est utilisable."""
        if self.page is None:
            return
        selectors = (
            READY_SELECTORS
            + self.selectors.attendance_button
            + self.selectors.login_username
        )
        await self._find_with_wait(selectors, timeout_ms)

    async def _find_with_wait(self, selectors: tuple[str, ...], timeout_ms: int):
        if self.page is None:
            return None
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            locator = await self._first_visible(selectors)
            if locator is not None:
                return locator
            await self.page.wait_for_timeout(200)
        return None

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
        # Attente adaptative : on repart des que le calendrier ou le formulaire
        # de connexion est la, au lieu d'un delai fixe.
        await self._wait_for_ready()

    async def _ensure_logged_in(self) -> None:
        if self.page is None:
            raise CesarError("navigateur non demarre")
        if self.config.cesar.login_path in self.page.url:
            await self.login()
            return

        username = await self._first_visible(self.selectors.login_username)
        password = await self._first_visible(self.selectors.login_password)
        if username is not None and password is not None:
            await self.login()

    async def login(self) -> None:
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
            await self._wait_for_ready()
        except LoginError:
            raise
        except Exception as exc:
            raise LoginError(f"connexion echouee : {exc}") from exc

        logger.info("connexion reussie")

    async def check(self) -> AttendanceSignal | None:
        """Rafraichit le tableau de bord et cherche le bouton d'emargement."""
        await self._goto_dashboard()
        await self._ensure_logged_in()

        button = await self._find_with_wait(self.selectors.attendance_button, 1500)
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
        except Exception:
            payload = {"action": "", "row": "", "label": ""}

        try:
            identity = await self.page.evaluate(CALENDAR_IDENTITY_JS)
            payload.update(identity)
        except Exception:
            logger.debug("identifiants calendrier indisponibles", exc_info=True)

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
        try:
            await canvas.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            logger.debug("canvas de signature deja visible", exc_info=True)

        box = await self._stable_box(canvas)
        if box is None or box["width"] <= 0 or box["height"] <= 0:
            raise SignError("canvas de signature sans dimensions")

        logger.info(
            "signature rejouee : %s points, canvas %sx%s",
            len(points),
            round(box["width"]),
            round(box["height"]),
        )
        diagnostics = SignatureDiagnostics(diagnostics_directory(), self.page)
        await diagnostics.begin(canvas)
        await self._draw_checked(canvas, box, points, diagnostics)
        await diagnostics.save(canvas)
        await self.page.wait_for_timeout(500)

        previous = await self._confirmation_text()
        confirm_button = await self._wait_for_selector(
            self.selectors.signature_save, 15000
        )
        await confirm_button.click()

        started = time.monotonic()
        confirmation = await self._wait_for_confirmation(previous, 15000)
        if confirmation is None:
            raise SignError("aucune confirmation affichee apres la signature")
        logger.info("confirmation du site : %s", confirmation)

        hidden = await self._wait_for_hidden(self.selectors.attendance_button, 15000)
        elapsed = time.monotonic() - started
        if not hidden:
            # Sur le vrai CESAR, apres l'enregistrement un nouveau popup s'ouvre
            # et ferme l'ancien sans retirer le bouton d'emargement du DOM. On
            # rafraichit alors la page : si l'emargement a bien ete pris en
            # compte, le bouton n'est plus present.
            logger.info(
                "bouton toujours visible %.1f s apres la signature, "
                "rafraichissement de la page pour verifier...",
                elapsed,
            )
            reload = getattr(self.page, "reload", None)
            if reload is not None:
                try:
                    await reload(wait_until="domcontentloaded")
                except Exception:
                    logger.debug("rafraichissement impossible", exc_info=True)
            if self.page is not None:
                await self.page.wait_for_timeout(500)
            still_visible = await self._first_visible(self.selectors.attendance_button)
            if still_visible is not None:
                raise SignError(
                    "bouton d'emargement toujours visible 15 s apres la signature"
                )
            logger.info(
                "bouton disparu apres rafraichissement, emargement pris en compte"
            )
        logger.info(
            "bouton d'emargement disparu apres %.1f s (confirmation : %s)",
            elapsed,
            confirmation,
        )
        return confirmation

    async def _stable_box(self, canvas, timeout_ms: int = 2000) -> dict | None:
        """Attend que le canvas cesse de bouger (animation de la popup)."""
        if self.page is None:
            return None
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        previous = await canvas.bounding_box()
        stable = 0
        while asyncio.get_running_loop().time() < deadline:
            await self.page.wait_for_timeout(80)
            current = await canvas.bounding_box()
            if current is None:
                continue
            if previous is not None and all(
                abs(current[key] - previous[key]) < 0.5
                for key in ("x", "y", "width", "height")
            ):
                stable += 1
                if stable >= 3:
                    return current
            else:
                stable = 0
            previous = current
        return previous

    async def _draw_checked(
        self,
        canvas,
        box: dict,
        points: list[Point],
        diagnostics: SignatureDiagnostics,
    ) -> None:
        """Rejoue la signature puis verifie qu'elle est vraiment dessinee.

        Un canvas mesure pendant une animation, ou un enchainement d'evenements
        ignore par la librairie du site, produit un simple point au lieu du
        trace. On retente alors en envoyant les evenements DOM directement.
        """
        await canvas.evaluate(INK_SNAPSHOT_JS)
        if await self._wait_until_hittable(canvas):
            box = await self._stable_box(canvas) or box
            await self._draw(box, self._fit_points(points, box))
        else:
            logger.warning(
                "canvas de signature toujours recouvert apres attente, "
                "envoi direct des evenements DOM"
            )
            await canvas.evaluate(
                EVENT_DRAW_JS, draw_coordinates(self._fit_points(points, box))
            )
        await self.page.wait_for_timeout(200)
        ink = await canvas.evaluate(INK_DIFF_JS)
        logger.info("encre detectee sur le canvas : %s", ink)
        await diagnostics.add_step("premier essai", canvas, ink)
        if not self._ink_is_incomplete(ink):
            return

        logger.warning(
            "trace incomplet sur le canvas CESAR (%s), nouvelle tentative", ink
        )
        retry_box = await self._stable_box(canvas)
        if retry_box is None or retry_box["width"] <= 0 or retry_box["height"] <= 0:
            raise SignError("canvas de signature sans dimensions")
        await canvas.evaluate(
            EVENT_DRAW_JS, draw_coordinates(self._fit_points(points, retry_box))
        )
        await self.page.wait_for_timeout(200)
        ink = await canvas.evaluate(INK_DIFF_JS)
        logger.info("encre detectee apres rejeu : %s", ink)
        await diagnostics.add_step("rejeu", canvas, ink)
        if self._ink_is_incomplete(ink):
            await diagnostics.save(canvas)
            raise SignError(
                "la signature n'a pas ete prise par le canvas CESAR "
                "(trace reduit a un point ou a une ligne)"
            )

    async def _wait_until_hittable(self, canvas, timeout_ms: int = 3000) -> bool:
        """Attend que l'animation de la popup decouvre le canvas.

        Pendant l'animation, une couche du site peut recouvrir le canvas : les
        clics de la souris partent alors sur cette couche et le trace est perdu.
        """
        if self.page is None:
            return await self._canvas_is_hittable(canvas)
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        waited = False
        while asyncio.get_running_loop().time() < deadline:
            if await self._canvas_is_hittable(canvas):
                if waited:
                    logger.info("canvas de signature decouvert apres attente")
                return True
            waited = True
            await self.page.wait_for_timeout(100)
        logger.warning("canvas de signature encore recouvert apres %sms", timeout_ms)
        return False

    async def _canvas_is_hittable(self, canvas) -> bool:
        """Verifie qu'aucun element ne recouvre le canvas.

        Si c'est le cas, la souris clique sur l'overlay : les evenements sont
        alors envoyes directement au canvas.
        """
        try:
            return bool(await canvas.evaluate(CANVAS_HITTABLE_JS))
        except Exception:
            return True

    def _fit_points(self, points: list[Point], box: dict) -> list[FittedPoint]:
        return fit_points(
            points,
            box["width"],
            box["height"],
            self.config.signature.padding_ratio,
        )

    @staticmethod
    def _ink_is_incomplete(ink: dict | None) -> bool:
        """Refuse un point ou une ligne a la place d'une signature."""
        if ink is None:
            return False
        if ink.get("count", 0) < 3:
            return True
        extent_x = _ink_ratio(ink, "minX", "maxX", "width")
        extent_y = _ink_ratio(ink, "minY", "maxY", "height")
        return min(extent_x, extent_y) < MIN_INK_RATIO

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

    async def _wait_for_hidden(
        self, selectors: tuple[str, ...], timeout_ms: int
    ) -> bool:
        """Attend qu'aucun des selecteurs ne soit plus visible."""
        if self.page is None:
            return False
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            locator = await self._first_visible(selectors)
            if locator is None:
                return True
            await self.page.wait_for_timeout(250)
        return await self._first_visible(selectors) is None

    async def _confirmation_text(self) -> str:
        if self.page is None:
            return ""
        locator = await self._first_visible(self.selectors.confirmation)
        if locator is None:
            return ""
        try:
            return (await locator.inner_text()).strip()
        except Exception:
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
