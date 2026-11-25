"""Detection CESAR en HTTP leger, signature conservee dans Chrome."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
from html.parser import HTMLParser
from urllib.parse import urlsplit

from curl_cffi import requests as curl_requests

from .cesar import AttendanceSignal, CesarError, CesarSession, SignError
from .config import Config

logger = logging.getLogger(__name__)

CALENDAR_ATTRIBUTES = (
    "data-tui-calendar-event-lesson-schedules-value",
    "data-tui-calendar-student-registration-value",
    "data-tui-calendar-max-time-attendance-value",
    "data-tui-calendar-time-server-value",
)
CHALLENGE_MARKERS = (
    "cf-challenge",
    "just a moment",
    "attention required",
    "g-recaptcha",
    "h-captcha",
)


class HttpTransportError(CesarError):
    """Le transport HTTP ne permet pas une detection fiable."""


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inputs: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = dict(attrs)
        name = values.get("name")
        if name:
            self.inputs.setdefault(name, []).append(values.get("value") or "")


class _CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if CALENDAR_ATTRIBUTES[0] in values:
            self.elements.append(values)


def _parse_inputs(text: str) -> dict[str, list[str]]:
    parser = _InputParser()
    parser.feed(text)
    return parser.inputs


def _first_input(inputs: dict[str, list[str]], name: str) -> str:
    values = inputs.get(name) or []
    if not values or not values[0]:
        raise HttpTransportError(f"champ de formulaire absent : {name}")
    return values[0]


def _parse_calendar(text: str) -> dict[str, str]:
    parser = _CalendarParser()
    parser.feed(text)
    if not parser.elements:
        raise HttpTransportError("calendrier CESAR absent de la reponse HTTP")
    attrs = parser.elements[0]
    missing = [name for name in CALENDAR_ATTRIBUTES if not attrs.get(name)]
    if missing:
        raise HttpTransportError("attributs du calendrier CESAR incomplets")
    return attrs


def _load_json(raw: str, description: str):
    try:
        return json.loads(html.unescape(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HttpTransportError(f"JSON {description} invalide") from exc


def _attendance_lines(node):
    lines = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "attendanceSheetLines" and isinstance(value, list):
                lines.extend(value)
            else:
                lines.extend(_attendance_lines(value))
    elif isinstance(node, list):
        for value in node:
            lines.extend(_attendance_lines(value))
    return lines


def _course_label(course: dict) -> str:
    description = course.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    subject = course.get("schoolSubject")
    if isinstance(subject, dict):
        for key in ("label", "name", "title", "shortName"):
            value = subject.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "Emargement ouvert"


def _signal_key(course: dict, line: dict, label: str) -> str:
    course_uuid = str(course.get("uuid") or "")
    line_uuid = str(line.get("uuid") or "")
    if course_uuid and line_uuid:
        basis = f"{course_uuid}|{line_uuid}"
    else:
        basis = "|".join((course_uuid, line_uuid, str(line.get("createdAt")), label))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _calendar_signal(attrs: dict[str, str]) -> AttendanceSignal | None:
    schedules = _load_json(attrs[CALENDAR_ATTRIBUTES[0]], "des cours")
    student = _load_json(attrs[CALENDAR_ATTRIBUTES[1]], "de l'etudiant")
    if not isinstance(schedules, list):
        raise HttpTransportError("format de la liste des cours inattendu")
    if not isinstance(student, dict) or not student.get("uuid"):
        raise HttpTransportError("identifiant etudiant absent du calendrier")
    try:
        max_minutes = int(attrs[CALENDAR_ATTRIBUTES[2]])
        server_now = int(attrs[CALENDAR_ATTRIBUTES[3]])
    except ValueError as exc:
        raise HttpTransportError("horloge du calendrier CESAR invalide") from exc

    student_uuid = student["uuid"]
    for course in schedules:
        if not isinstance(course, dict):
            continue
        for line in _attendance_lines(course):
            if not isinstance(line, dict):
                continue
            subscription = line.get("planningGroupSubscription") or {}
            if not isinstance(subscription, dict):
                raise HttpTransportError("inscription CESAR invalide")
            registration = subscription.get("studentRegistration") or {}
            if not isinstance(registration, dict):
                raise HttpTransportError("inscription etudiant CESAR invalide")
            if registration.get("uuid") != student_uuid:
                continue
            signature = line.get("signature")
            signed = bool(
                (isinstance(signature, dict) and signature.get("signed") is True)
                or line.get("attendanceWithoutSignature") is True
            )
            if signed or line.get("signingOff") is not True:
                continue
            created_at = line.get("createdAt")
            if not isinstance(created_at, int):
                raise HttpTransportError("date d'emargement CESAR invalide")
            seconds_left = round(
                (created_at + max_minutes * 60_000 - server_now * 1000) / 1000
            )
            if seconds_left <= 0:
                continue
            label = _course_label(course)
            logger.info("emargement HTTP detecte : %s", label)
            return AttendanceSignal(_signal_key(course, line, label), label)
    return None


class HttpCesarSession:
    """Session HTTP pour detecter, session Chrome pour signer."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.headless = config.watcher.headless
        self._session = None
        self._browser: CesarSession | None = None

    async def open(self, headless: bool | None = None) -> None:
        self.headless = self.config.watcher.headless if headless is None else headless
        try:
            await asyncio.to_thread(self._open_http)
        except HttpTransportError:
            raise
        except Exception as exc:
            raise HttpTransportError("ouverture de la session HTTP impossible") from exc

    def _open_http(self) -> None:
        self._session = curl_requests.Session(impersonate="chrome")
        cookies = self._load_cookies()
        if cookies:
            self._session.cookies.update(cookies)
        if not cookies.get("PHPSESSID"):
            self._login()

    def _load_cookies(self) -> dict[str, str]:
        path = self.config.watcher.http_cookies_file
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in data.items()
        ):
            return {}
        return data

    def _save_cookies(self) -> None:
        if self._session is None:
            return
        path = self.config.watcher.http_cookies_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self._session.cookies.get_dict()),
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(path)
            path.chmod(0o600)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def _raise_for_status(self, response) -> None:
        status = response.status_code
        if status in (403, 429) or status >= 500:
            detail = ""
            if status == 429 and response.headers.get("Retry-After"):
                detail = f", Retry-After={response.headers['Retry-After']}"
            raise HttpTransportError(f"CESAR HTTP {status}{detail}")
        if status >= 400:
            raise HttpTransportError(f"CESAR HTTP {status}")
        lowered = response.text.lower()
        if any(marker in lowered for marker in CHALLENGE_MARKERS):
            raise HttpTransportError(
                "challenge CESAR detecte, detection HTTP interrompue"
            )

    def _is_login_path(self, path: str) -> bool:
        login_path = self.config.cesar.login_path.rstrip("/")
        return path == login_path or path.startswith(login_path + "/")

    def _login(self) -> None:
        if self._session is None:
            raise HttpTransportError("session HTTP non ouverte")
        logger.info("connexion HTTP a CESAR")
        page = self._session.get(
            self.config.cesar.login_url,
            timeout=45,
            allow_redirects=True,
        )
        self._raise_for_status(page)
        csrf = _first_input(_parse_inputs(page.text), "_csrf_token")
        response = self._session.post(
            self.config.cesar.login_url,
            data={
                "_username": self.config.cesar.username.strip(),
                "_password": self.config.cesar.password,
                "_csrf_token": csrf,
                "_referer": "",
            },
            headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Origin": self.config.cesar.base_url,
                "Referer": self.config.cesar.login_url,
            },
            timeout=45,
            allow_redirects=True,
        )
        self._raise_for_status(response)
        path = urlsplit(str(response.url)).path
        if self._is_login_path(path):
            raise HttpTransportError("identifiants CESAR refuses par le transport HTTP")
        if "/upload/cvec" in path:
            self._skip_cvec(response)
        self._save_cookies()
        logger.info("connexion HTTP reussie")

    def _skip_cvec(self, response) -> None:
        token = _first_input(
            _parse_inputs(response.text),
            "cvec_file[_token]",
        )
        skipped = self._session.post(
            response.url,
            data={
                "cvec_file[skip]": "skip",
                "cvec_file[_token]": token,
            },
            timeout=45,
            allow_redirects=True,
        )
        self._raise_for_status(skipped)
        path = urlsplit(str(skipped.url)).path
        if self._is_login_path(path) or "/upload/cvec" in path:
            raise HttpTransportError("impossible de terminer l'etape CVEC")

    def _check_http(self) -> AttendanceSignal | None:
        if self._session is None:
            raise HttpTransportError("session HTTP non ouverte")
        response = self._session.get(
            self.config.cesar.dashboard_url,
            timeout=45,
            allow_redirects=True,
        )
        self._raise_for_status(response)
        path = urlsplit(str(response.url)).path
        if self._is_login_path(path):
            self._login()
            response = self._session.get(
                self.config.cesar.dashboard_url,
                timeout=45,
                allow_redirects=True,
            )
            self._raise_for_status(response)
            if self._is_login_path(urlsplit(str(response.url)).path):
                raise HttpTransportError("session HTTP CESAR expirmee")
        return _calendar_signal(_parse_calendar(response.text))

    async def check(self) -> AttendanceSignal | None:
        if self._browser is not None:
            return await self._browser.check()
        try:
            return await asyncio.to_thread(self._check_http)
        except HttpTransportError:
            raise
        except Exception as exc:
            raise HttpTransportError("detection HTTP CESAR impossible") from exc

    async def _open_browser(self, headless: bool) -> None:
        browser = CesarSession(self.config)
        try:
            await browser.open(headless=headless)
            await self._inject_cookie(browser)
        except Exception:
            await browser.close()
            raise
        self._browser = browser

    async def _inject_cookie(self, browser: CesarSession) -> None:
        if self._session is None or browser._context is None:
            raise HttpTransportError("session HTTP ou navigateur indisponible")
        cookie = self._session.cookies.get("PHPSESSID")
        if not cookie:
            raise HttpTransportError("cookie de session HTTP absent")
        host = urlsplit(self.config.cesar.base_url).hostname
        if not host:
            raise HttpTransportError("hote CESAR invalide")
        await browser._context.add_cookies(
            [
                {
                    "name": "PHPSESSID",
                    "value": cookie,
                    "domain": host,
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )

    async def _close_browser(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None

    async def switch_headless(self, headless: bool) -> None:
        if headless:
            await self._close_browser()
            return
        if self._browser is not None and not self._browser.headless:
            return
        await self._close_browser()
        await self._open_browser(headless=False)

    async def sign(self, points: list) -> str:
        if self._browser is not None:
            return await self._browser.sign(points)
        await self._open_browser(headless=self.config.watcher.headless)
        try:
            signal = await self._browser.check()
            if signal is None:
                raise SignError("emargement introuvable dans Chrome")
            return await self._browser.sign(points)
        finally:
            await self._close_browser()

    async def restart(self) -> None:
        await self.close()
        await self.open()

    async def close(self) -> None:
        await self._close_browser()
        if self._session is not None:
            await asyncio.to_thread(self._session.close)
            self._session = None
