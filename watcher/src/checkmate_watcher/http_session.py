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


def _cvec_payload(response) -> dict:
    token = _first_input(_parse_inputs(response.text), "cvec_file[_token]")
    return {"cvec_file[skip]": "skip", "cvec_file[_token]": token}


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
    if isinstance(node, list):
        return _attendance_lines_from_list(node)
    if not isinstance(node, dict):
        return []
    return _attendance_lines_from_dict(node)


def _attendance_lines_from_list(values: list) -> list:
    return [line for value in values for line in _attendance_lines(value)]


def _attendance_lines_from_dict(values: dict) -> list:
    lines = []
    for key, value in values.items():
        if key == "attendanceSheetLines" and isinstance(value, list):
            lines.extend(value)
        else:
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


def _calendar_json(attrs: dict[str, str]) -> tuple[list, dict]:
    schedules = _load_json(attrs[CALENDAR_ATTRIBUTES[0]], "des cours")
    student = _load_json(attrs[CALENDAR_ATTRIBUTES[1]], "de l'etudiant")
    if not isinstance(schedules, list):
        raise HttpTransportError("format de la liste des cours inattendu")
    if not isinstance(student, dict) or not student.get("uuid"):
        raise HttpTransportError("identifiant etudiant absent du calendrier")
    return schedules, student


def _calendar_clock(attrs: dict[str, str]) -> tuple[int, int]:
    try:
        max_minutes = int(attrs[CALENDAR_ATTRIBUTES[2]])
        server_now = int(attrs[CALENDAR_ATTRIBUTES[3]])
    except ValueError as exc:
        raise HttpTransportError("horloge du calendrier CESAR invalide") from exc
    return max_minutes, server_now


def _calendar_settings(attrs: dict[str, str]) -> tuple[list, str, int, int]:
    schedules, student = _calendar_json(attrs)
    max_minutes, server_now = _calendar_clock(attrs)
    return schedules, student["uuid"], max_minutes, server_now


def _line_registration(line: dict) -> dict:
    subscription = line.get("planningGroupSubscription") or {}
    if not isinstance(subscription, dict):
        raise HttpTransportError("inscription CESAR invalide")
    registration = subscription.get("studentRegistration") or {}
    if not isinstance(registration, dict):
        raise HttpTransportError("inscription etudiant CESAR invalide")
    return registration


def _matching_lines(course: dict, student_uuid: str) -> list[dict]:
    lines = []
    for line in _attendance_lines(course):
        if not isinstance(line, dict):
            continue
        if _line_registration(line).get("uuid") == student_uuid:
            lines.append(line)
    return lines


def _line_signed(line: dict) -> bool:
    signature = line.get("signature")
    if isinstance(signature, dict) and signature.get("signed") is True:
        return True
    return line.get("attendanceWithoutSignature") is True


def _line_seconds_left(line: dict, max_minutes: int, server_now: int) -> int:
    created_at = line.get("createdAt")
    if not isinstance(created_at, int):
        raise HttpTransportError("date d'emargement CESAR invalide")
    return round((created_at + max_minutes * 60_000 - server_now * 1000) / 1000)


def _open_line(course: dict, student_uuid: str, max_minutes: int, server_now: int):
    for line in _matching_lines(course, student_uuid):
        if _line_signed(line) or line.get("signingOff") is not True:
            continue
        if _line_seconds_left(line, max_minutes, server_now) > 0:
            return line
    return None


def _attendance_signal(course: dict, line: dict) -> AttendanceSignal:
    label = _course_label(course)
    logger.info("emargement HTTP detecte : %s", label)
    return AttendanceSignal(_signal_key(course, line, label), label)


def _calendar_signal(attrs: dict[str, str]) -> AttendanceSignal | None:
    schedules, student_uuid, max_minutes, server_now = _calendar_settings(attrs)
    for course in schedules:
        if not isinstance(course, dict):
            continue
        line = _open_line(course, student_uuid, max_minutes, server_now)
        if line is not None:
            return _attendance_signal(course, line)
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


def _cookie_values(data: dict) -> tuple:
    domain = data["domain"]
    return (
        (0, data["name"], data["value"], None, False, domain, True)
        + (
            domain.startswith("."),
            data["path"],
            True,
            data["secure"],
            data.get("expires"),
        )
        + (data.get("discard", True), None, None, data.get("rest") or {}, False)
    )


def _cookie_from_data(data: dict) -> Cookie:
    return Cookie(*_cookie_values(data))


def _domain_allowed(host: str, domain: str) -> bool:
    normalized = domain.lstrip(".").lower()
    return host == normalized or host.endswith("." + normalized)


def _read_cookie_data(path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _cookie_data_expired(item: dict) -> bool:
    expires = item.get("expires")
    if expires is not None and not isinstance(expires, (int, float)):
        return True
    return expires is not None and expires <= time.time()


def _cookie_strings_valid(item: dict) -> bool:
    return all(
        isinstance(item.get(key), str) for key in ("name", "value", "domain", "path")
    )


def _cookie_security_valid(item: dict, host: str) -> bool:
    if not isinstance(item.get("secure"), bool):
        return False
    if not item["domain"] or not _domain_allowed(host, item["domain"]):
        return False
    return not _cookie_data_expired(item)


def _cookie_data_valid(item: dict, host: str) -> bool:
    if not isinstance(item, dict):
        return False
    if not _cookie_strings_valid(item):
        return False
    if not _cookie_security_valid(item, host):
        return False
    return isinstance(item.get("rest", {}), dict)


def _replace_private_json(temporary, path, data) -> None:
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    temporary.replace(path)
    path.chmod(0o600)


def _write_private_json(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        _replace_private_json(temporary, path, data)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


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
            logger.debug("echec de l'ouverture HTTP", exc_info=True)
            raise HttpTransportError("ouverture de la session HTTP impossible") from exc

    def _open_http(self) -> None:
        self._session = curl_requests.Session(impersonate="chrome")
        for cookie in self._load_cookies():
            self._session.cookies.jar.set_cookie(cookie)
        if not self._session.cookies.get("PHPSESSID"):
            self._login()

    def _load_cookies(self) -> list[Cookie]:
        data = _read_cookie_data(self.config.watcher.http_cookies_file)
        host = urlsplit(self.config.cesar.base_url).hostname or ""
        return [
            _cookie_from_data(item) for item in data if _cookie_data_valid(item, host)
        ]

    def _save_cookies(self) -> None:
        if self._session is None:
            return
        cookies = [_cookie_data(cookie) for cookie in self._session.cookies.jar]
        _write_private_json(self.config.watcher.http_cookies_file, cookies)

    def _require_http_session(self):
        if self._session is None:
            raise HttpTransportError("session HTTP non ouverte")
        return self._session

    def _http_status_error(self, response) -> HttpTransportError:
        status = response.status_code
        detail = ""
        if status == 429 and response.headers.get("Retry-After"):
            detail = f", Retry-After={response.headers['Retry-After']}"
        return HttpTransportError(f"CESAR HTTP {status}{detail}")

    def _raise_for_status(self, response) -> None:
        status = response.status_code
        if status in (403, 429) or status >= 500:
            raise self._http_status_error(response)
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

    def _login_form(self) -> str:
        session = self._require_http_session()
        page = session.get(
            self.config.cesar.login_url, timeout=45, allow_redirects=True
        )
        self._raise_for_status(page)
        return _first_input(_parse_inputs(page.text), "_csrf_token")

    def _login_payload(self, csrf: str) -> dict:
        return {
            "_username": self.config.cesar.username.strip(),
            "_password": self.config.cesar.password,
            "_csrf_token": csrf,
            "_referer": "",
        }

    def _login_headers(self) -> dict:
        return {
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": self.config.cesar.base_url,
            "Referer": self.config.cesar.login_url,
        }

    def _post_login(self, csrf: str):
        session = self._require_http_session()
        return session.post(
            self.config.cesar.login_url,
            data=self._login_payload(csrf),
            headers=self._login_headers(),
            timeout=45,
            allow_redirects=True,
        )

    def _finish_login(self, response) -> None:
        self._raise_for_status(response)
        path = urlsplit(str(response.url)).path
        if self._is_login_path(path):
            raise HttpTransportError("identifiants CESAR refuses par le transport HTTP")
        if "/upload/cvec" in path:
            self._skip_cvec(response)
        self._save_cookies()
        logger.info("connexion HTTP reussie")

    def _login(self) -> None:
        logger.info("connexion HTTP a CESAR")
        csrf = self._login_form()
        self._finish_login(self._post_login(csrf))

    def _post_cvec_skip(self, response):
        session = self._require_http_session()
        return session.post(
            response.url,
            data=_cvec_payload(response),
            timeout=45,
            allow_redirects=True,
        )

    def _skip_cvec(self, response) -> None:
        skipped = self._post_cvec_skip(response)
        self._raise_for_status(skipped)
        path = urlsplit(str(skipped.url)).path
        if self._is_login_path(path) or "/upload/cvec" in path:
            raise HttpTransportError("impossible de terminer l'etape CVEC")

    def _dashboard_response(self):
        session = self._require_http_session()
        response = session.get(
            self.config.cesar.dashboard_url, timeout=45, allow_redirects=True
        )
        self._raise_for_status(response)
        return response

    def _refresh_http_session(self):
        self._login()
        response = self._dashboard_response()
        if self._is_login_path(urlsplit(str(response.url)).path):
            raise HttpTransportError("session HTTP CESAR expiree")
        return response

    def _check_http(self) -> AttendanceSignal | None:
        response = self._dashboard_response()
        if self._is_login_path(urlsplit(str(response.url)).path):
            response = self._refresh_http_session()
        return _calendar_signal(_parse_calendar(response.text))

    async def check(self) -> AttendanceSignal | None:
        if self._browser is not None:
            return await self._browser.check()
        try:
            return await self._run_worker(self._check_http)
        except HttpTransportError:
            raise
        except Exception as exc:
            logger.debug("echec de la detection HTTP", exc_info=True)
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
