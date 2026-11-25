"""Detection CESAR en HTTP leger, signature conservee dans Chrome."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from html.parser import HTMLParser
from http.cookiejar import Cookie
from urllib.parse import urlsplit

from curl_cffi import requests as curl_requests

from .cesar import (
    AttendanceSignal,
    CesarError,
    CesarSession,
    SignError,
    signal_key,
)
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
        return json.loads(raw)
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
    return signal_key(
        {
            "course_uuid": str(course.get("uuid") or ""),
            "line_uuid": str(line.get("uuid") or ""),
            "label": label,
            "row": str(line.get("createdAt") or ""),
        }
    )


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


def _cookie_data(cookie: Cookie) -> dict:
    return {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "secure": cookie.secure,
        "expires": cookie.expires,
        "discard": cookie.discard,
        "rest": dict(cookie._rest),
    }


def _cookie_from_data(data: dict) -> Cookie:
    return Cookie(
        version=0,
        name=data["name"],
        value=data["value"],
        port=None,
        port_specified=False,
        domain=data["domain"],
        domain_specified=True,
        domain_initial_dot=data["domain"].startswith("."),
        path=data["path"],
        path_specified=True,
        secure=data["secure"],
        expires=data.get("expires"),
        discard=data.get("discard", True),
        comment=None,
        comment_url=None,
        rest=data.get("rest") or {},
        rfc2109=False,
    )


def _domain_allowed(host: str, domain: str) -> bool:
    normalized = domain.lstrip(".").lower()
    return host == normalized or host.endswith("." + normalized)


class HttpCesarSession:
    """Session HTTP pour detecter, session Chrome pour signer."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.headless = config.watcher.headless
        self._session = None
        self._browser: CesarSession | None = None
        self._workers: set[asyncio.Task] = set()

    async def _run_worker(self, function):
        worker = asyncio.create_task(asyncio.to_thread(function))
        self._workers.add(worker)
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            except Exception:
                logger.debug("worker HTTP interrompu", exc_info=True)
            raise
        finally:
            self._workers.discard(worker)

    async def open(self, headless: bool | None = None) -> None:
        self.headless = self.config.watcher.headless if headless is None else headless
        try:
            await self._run_worker(self._open_http)
        except asyncio.CancelledError:
            await self.close()
            raise
        except HttpTransportError:
            raise
        except Exception as exc:
            raise HttpTransportError("ouverture de la session HTTP impossible") from exc

    def _open_http(self) -> None:
        self._session = curl_requests.Session(impersonate="chrome")
        for cookie in self._load_cookies():
            self._session.cookies.jar.set_cookie(cookie)
        if not self._session.cookies.get("PHPSESSID"):
            self._login()

    def _load_cookies(self) -> list[Cookie]:
        path = self.config.watcher.http_cookies_file
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        host = urlsplit(self.config.cesar.base_url).hostname or ""
        cookies = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if not all(
                isinstance(item.get(key), str)
                for key in ("name", "value", "domain", "path")
            ):
                continue
            if not isinstance(item.get("secure"), bool):
                continue
            if not item["domain"] or not _domain_allowed(host, item["domain"]):
                continue
            expires = item.get("expires")
            if expires is not None and not isinstance(expires, (int, float)):
                continue
            if expires is not None and expires <= time.time():
                continue
            if not isinstance(item.get("rest", {}), dict):
                continue
            cookies.append(_cookie_from_data(item))
        return cookies

    def _save_cookies(self) -> None:
        if self._session is None:
            return
        path = self.config.watcher.http_cookies_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        cookies = [_cookie_data(cookie) for cookie in self._session.cookies.jar]
        try:
            temporary.unlink(missing_ok=True)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(cookies, handle)
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
            return await self._run_worker(self._check_http)
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
        host = urlsplit(self.config.cesar.base_url).hostname
        if not host:
            raise HttpTransportError("hote CESAR invalide")
        cookie = next(
            (
                item
                for item in self._session.cookies.jar
                if item.name == "PHPSESSID" and _domain_allowed(host, item.domain)
            ),
            None,
        )
        if cookie is None:
            raise HttpTransportError("cookie de session HTTP absent")
        same_site = cookie._rest.get("SameSite") or "Lax"
        await browser._context.add_cookies(
            [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires or -1,
                    "httpOnly": "HttpOnly" in cookie._rest,
                    "sameSite": same_site,
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
        workers = [
            worker for worker in self._workers if worker is not asyncio.current_task()
        ]
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        if self._session is not None:
            await self._run_worker(self._session.close)
            self._session = None
