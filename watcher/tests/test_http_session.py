from __future__ import annotations

import asyncio
import html
import json
import stat
from dataclasses import replace

import pytest
from curl_cffi.requests.cookies import Cookies

from checkmate_watcher import http_session
from checkmate_watcher.config import (
    CesarConfig,
    Config,
    NotificationConfig,
    Selectors,
    SignatureConfig,
    WatcherConfig,
)
from checkmate_watcher.http_session import HttpCesarSession, HttpTransportError

SERVER_NOW = 1_700_000_000


class FakeResponse:
    def __init__(
        self,
        text: str,
        *,
        status: int = 200,
        url: str = "https://cesar.example.fr/",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.status_code = status
        self.url = url
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.cookies = Cookies()
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    def _response(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("reponse HTTP de test manquante")
        return self.responses.pop(0)

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self._response("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> FakeResponse:
        return self._response("POST", url, **kwargs)

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.cookies: list[dict] = []

    async def add_cookies(self, cookies: list[dict]) -> None:
        self.cookies.extend(cookies)


class FakeBrowser:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.headless = True
        self._context = FakeContext()
        self.opened_with = None
        self.closed = False

    async def open(self, headless: bool) -> None:
        self.headless = headless
        self.opened_with = headless

    async def close(self) -> None:
        self.closed = True

    async def check(self):
        return object()

    async def sign(self, points: list) -> str:
        return "signature confirmee"


def make_config(tmp_path, **watcher_values) -> Config:
    watcher = WatcherConfig(
        http_cookies_file=tmp_path / "http-cookies.json",
        **watcher_values,
    )
    return Config(
        cesar=CesarConfig(
            base_url="https://cesar.example.fr",
            username="eleve",
            password="secret",
        ),
        watcher=watcher,
        signature=SignatureConfig(),
        notifications=NotificationConfig(),
        selectors=Selectors.from_dict({}),
    )


def attendance_line(
    uuid: str,
    *,
    student_uuid: str = "student-1",
    signing_off: bool = True,
    signed: bool = False,
    created_at: int = SERVER_NOW * 1000 - 60_000,
) -> dict:
    return {
        "uuid": uuid,
        "createdAt": created_at,
        "signingOff": signing_off,
        "signature": {"signed": True} if signed else None,
        "attendanceWithoutSignature": False,
        "planningGroupSubscription": {"studentRegistration": {"uuid": student_uuid}},
    }


def course(uuid: str, lines: list[dict], label: str = "Cours de test") -> dict:
    return {
        "uuid": uuid,
        "description": label,
        "attendanceSheet": {"attendanceSheetLines": lines},
    }


def calendar_html(
    courses: list[dict],
    *,
    student_uuid: str = "student-1",
    max_minutes: int = 5,
    server_now: int = SERVER_NOW,
) -> str:
    values = {
        http_session.CALENDAR_ATTRIBUTES[0]: courses,
        http_session.CALENDAR_ATTRIBUTES[1]: {"uuid": student_uuid},
        http_session.CALENDAR_ATTRIBUTES[2]: max_minutes,
        http_session.CALENDAR_ATTRIBUTES[3]: server_now,
    }
    attrs = " ".join(
        f'{name}="{html.escape(json.dumps(value), quote=True)}"'
        for name, value in values.items()
    )
    return f'<div data-controller="tui-calendar" {attrs}></div>'


def login_html(token: str = "csrf") -> str:
    return f'<input name="_csrf_token" value="{token}">'


def test_detecte_uniquement_l_emargement_ouvert_de_l_etudiant(tmp_path):
    courses = [
        course(
            "other",
            [attendance_line("other-line", student_uuid="student-2")],
            "Autre etudiant",
        ),
        course("signed", [attendance_line("signed-line", signed=True)], "Signe"),
        course(
            "expired",
            [
                attendance_line(
                    "expired-line",
                    created_at=SERVER_NOW * 1000 - 600_000,
                )
            ],
            "Expire",
        ),
        course("open", [attendance_line("open-line")], "Cours ouvert"),
    ]
    session = HttpCesarSession(make_config(tmp_path))
    session._session = FakeSession([FakeResponse(calendar_html(courses))])

    signal = asyncio.run(session.check())

    assert signal is not None
    assert signal.label == "Cours ouvert"
    assert signal.key == http_session._signal_key(
        courses[-1],
        courses[-1]["attendanceSheet"]["attendanceSheetLines"][0],
        signal.label,
    )


def test_absence_de_calendrier_ne_renvoie_pas_aucun_emargement(tmp_path):
    session = HttpCesarSession(make_config(tmp_path))
    session._session = FakeSession([FakeResponse("<html>Accueil</html>")])

    with pytest.raises(HttpTransportError, match="calendrier CESAR absent"):
        asyncio.run(session.check())


@pytest.mark.parametrize("status", (403, 429, 500))
def test_statut_http_bloquant_declenche_une_erreur(tmp_path, status):
    session = HttpCesarSession(make_config(tmp_path))
    session._session = FakeSession(
        [FakeResponse("", status=status, headers={"Retry-After": "30"})]
    )

    with pytest.raises(HttpTransportError, match=f"CESAR HTTP {status}"):
        asyncio.run(session.check())


def test_challenge_detecte_declenche_une_erreur(tmp_path):
    session = HttpCesarSession(make_config(tmp_path))
    session._session = FakeSession(
        [FakeResponse('<div id="cf-challenge">Verification</div>')]
    )

    with pytest.raises(HttpTransportError, match="challenge CESAR"):
        asyncio.run(session.check())


def test_session_expiree_relance_le_login(tmp_path):
    config = make_config(tmp_path)
    dashboard = calendar_html([course("open", [attendance_line("line")])])
    fake = FakeSession(
        [
            FakeResponse(
                login_html(),
                url=config.cesar.login_url,
            ),
            FakeResponse(login_html("new-csrf"), url=config.cesar.login_url),
            FakeResponse(dashboard),
            FakeResponse(dashboard),
        ]
    )
    fake.cookies.set("PHPSESSID", "expired", domain="cesar.example.fr", secure=True)
    session = HttpCesarSession(config)
    session._session = fake

    signal = asyncio.run(session.check())

    assert signal is not None
    assert [method for method, _, _ in fake.calls] == ["GET", "GET", "POST", "GET"]
    assert fake.calls[2][2]["data"]["_csrf_token"] == "new-csrf"
    assert config.watcher.http_cookies_file.is_file()


def test_login_refuse_declenche_une_erreur(tmp_path):
    config = make_config(tmp_path)
    fake = FakeSession(
        [
            FakeResponse(login_html(), url=config.cesar.login_url),
            FakeResponse(login_html(), url=config.cesar.login_url),
        ]
    )
    session = HttpCesarSession(config)
    session._session = fake

    with pytest.raises(HttpTransportError, match="identifiants CESAR refuses"):
        session._login()


def test_etape_cvec_est_ignoree_une_fois(tmp_path):
    config = make_config(tmp_path)
    cvec_url = "https://cesar.example.fr/upload/cvec"
    fake = FakeSession(
        [
            FakeResponse(login_html(), url=config.cesar.login_url),
            FakeResponse(
                '<input name="cvec_file[_token]" value="cvec-csrf">',
                url=cvec_url,
            ),
            FakeResponse("<html>Accueil</html>"),
        ]
    )
    session = HttpCesarSession(config)
    session._session = fake

    session._login()

    assert fake.calls[2][0] == "POST"
    assert fake.calls[2][2]["data"] == {
        "cvec_file[skip]": "skip",
        "cvec_file[_token]": "cvec-csrf",
    }


def test_cookies_http_sont_persistes_avec_permissions_restreintes(tmp_path):
    config = make_config(tmp_path)
    fake = FakeSession(
        [
            FakeResponse(login_html(), url=config.cesar.login_url),
            FakeResponse("<html>Accueil</html>"),
        ]
    )
    fake.cookies.set(
        "PHPSESSID", "session-secret", domain="cesar.example.fr", secure=True
    )
    session = HttpCesarSession(config)
    session._session = fake

    session._login()

    saved = json.loads(config.watcher.http_cookies_file.read_text(encoding="utf-8"))
    assert saved[0]["name"] == "PHPSESSID"
    assert saved[0]["value"] == "session-secret"
    assert saved[0]["domain"] == "cesar.example.fr"
    assert saved[0]["path"] == "/"
    assert saved[0]["secure"] is True
    mode = stat.S_IMODE(config.watcher.http_cookies_file.stat().st_mode)
    assert mode == 0o600


def test_cookies_persistants_evitent_un_nouveau_login(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    config.watcher.http_cookies_file.write_text(
        json.dumps(
            [
                {
                    "name": "PHPSESSID",
                    "value": "saved",
                    "domain": "cesar.example.fr",
                    "path": "/",
                    "secure": True,
                    "expires": None,
                    "rest": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    fake = FakeSession([])
    monkeypatch.setattr(http_session.curl_requests, "Session", lambda **kwargs: fake)
    session = HttpCesarSession(config)

    asyncio.run(session.open())

    assert fake.calls == []
    assert fake.cookies.get("PHPSESSID") == "saved"


def test_cookies_d_un_autre_domaine_sont_ignores(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    config.watcher.http_cookies_file.write_text(
        json.dumps(
            [
                {
                    "name": "PHPSESSID",
                    "value": "saved",
                    "domain": "cesar.example.fr",
                    "path": "/",
                    "secure": True,
                    "expires": None,
                    "rest": {},
                },
                {
                    "name": "FOREIGN",
                    "value": "secret",
                    "domain": "example.org",
                    "path": "/",
                    "secure": True,
                    "expires": None,
                    "rest": {},
                },
            ]
        ),
        encoding="utf-8",
    )
    fake = FakeSession([])
    monkeypatch.setattr(http_session.curl_requests, "Session", lambda **kwargs: fake)
    session = HttpCesarSession(config)

    asyncio.run(session.open())

    names = {cookie.name for cookie in fake.cookies.jar}
    assert names == {"PHPSESSID"}


def test_cookie_http_non_secure_reste_non_secure_dans_chrome(tmp_path, monkeypatch):
    browsers: list[FakeBrowser] = []

    def browser_factory(config):
        browser = FakeBrowser(config)
        browsers.append(browser)
        return browser

    config = make_config(tmp_path)
    config = replace(
        config, cesar=replace(config.cesar, base_url="http://cesar.example.fr")
    )
    monkeypatch.setattr(http_session, "CesarSession", browser_factory)
    session = HttpCesarSession(config)
    session._session = FakeSession([])
    session._session.cookies.set(
        "PHPSESSID", "shared-session", domain="cesar.example.fr", secure=False
    )

    asyncio.run(session.switch_headless(False))

    assert browsers[0]._context.cookies[0]["secure"] is False


def test_cookie_http_est_injecte_dans_chrome(tmp_path, monkeypatch):
    browsers: list[FakeBrowser] = []

    def browser_factory(config):
        browser = FakeBrowser(config)
        browsers.append(browser)
        return browser

    monkeypatch.setattr(http_session, "CesarSession", browser_factory)
    session = HttpCesarSession(make_config(tmp_path))
    session._session = FakeSession([])
    session._session.cookies.set(
        "PHPSESSID", "shared-session", domain="cesar.example.fr", secure=True
    )

    asyncio.run(session.switch_headless(False))

    assert browsers[0].opened_with is False
    assert browsers[0]._context.cookies[0]["name"] == "PHPSESSID"
    assert browsers[0]._context.cookies[0]["value"] == "shared-session"
    assert browsers[0]._context.cookies[0]["domain"] == "cesar.example.fr"


def test_signature_invisible_ouvvre_et_ferme_chrome(tmp_path, monkeypatch):
    browsers: list[FakeBrowser] = []

    def browser_factory(config):
        browser = FakeBrowser(config)
        browsers.append(browser)
        return browser

    monkeypatch.setattr(http_session, "CesarSession", browser_factory)
    session = HttpCesarSession(make_config(tmp_path, headless=True))
    session._session = FakeSession([])
    session._session.cookies.set(
        "PHPSESSID", "shared-session", domain="cesar.example.fr", secure=True
    )

    result = asyncio.run(session.sign([]))

    assert result == "signature confirmee"
    assert browsers[0].opened_with is True
    assert browsers[0].closed is True
