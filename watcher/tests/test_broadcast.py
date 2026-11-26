from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from checkmate_watcher import broadcast, watcher
from checkmate_watcher.broadcast import Message


def test_parse_ignore_les_entrees_inutilisables():
    payload = {
        "messages": [
            {"id": 3, "title": " Titre ", "message": " Texte "},
            {"id": 0, "title": "Zero", "message": "Ignore"},
            {"id": True, "title": "Bool", "message": "Ignore"},
            {"id": 4, "title": "", "message": "Sans titre"},
            {"id": 5, "title": "Sans texte", "message": ""},
            "pas un objet",
        ]
    }
    assert broadcast.parse_messages(payload) == [Message(3, "Titre", "Texte")]


@pytest.mark.parametrize("payload", [None, [], {}, {"messages": "x"}])
def test_parse_tolere_une_reponse_inattendue(payload):
    assert broadcast.parse_messages(payload) == []


def test_unseen_trie_par_identifiant():
    messages = [Message(5, "C", "c"), Message(2, "A", "a")]
    assert broadcast.unseen(messages, 2) == [Message(5, "C", "c")]
    assert broadcast.newest_id(messages) == 5
    assert broadcast.newest_id([]) == 0


class _State:
    def __init__(self) -> None:
        self.meta: dict[str, str] = {}

    def get_meta(self, key: str):
        return self.meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self.meta[key] = value


def _config(*, enabled: bool = True):
    return SimpleNamespace(
        notifications=SimpleNamespace(enabled=True),
        broadcast=SimpleNamespace(
            enabled=enabled, endpoint="https://example.test/api/messages"
        ),
    )


def _messages(*ids: int) -> list[Message]:
    return [
        Message(message_id, f"Titre {message_id}", "Texte")
        for message_id in ids
    ]


def _patch_fetch(monkeypatch, messages, calls=None):
    def fetch(endpoint, *, timeout=None):
        if calls is not None:
            calls.append(endpoint)
        return messages

    monkeypatch.setattr(broadcast, "fetch_messages", fetch)


def _patch_send(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def send(config, title, message, **kwargs):
        sent.append((title, message))
        return True

    monkeypatch.setattr(watcher, "_send", send)
    return sent


def test_premier_contact_retient_l_existant(monkeypatch):
    _patch_fetch(monkeypatch, _messages(3, 7))
    sent = _patch_send(monkeypatch)
    state = _State()

    asyncio.run(watcher._check_broadcast(_config(), state))

    assert sent == []
    assert state.meta["broadcast.last_id"] == "7"
    assert state.meta["broadcast.initialized"] == "1"


def test_les_nouveaux_messages_sont_notifies(monkeypatch):
    _patch_fetch(monkeypatch, _messages(2, 5, 6))
    sent = _patch_send(monkeypatch)
    state = _State()
    state.meta.update({"broadcast.initialized": "1", "broadcast.last_id": "2"})

    asyncio.run(watcher._check_broadcast(_config(), state))

    assert [title for title, _ in sent] == ["Titre 5", "Titre 6"]
    assert state.meta["broadcast.last_id"] == "6"


def test_les_notifications_sont_plafonnees(monkeypatch):
    _patch_fetch(monkeypatch, _messages(1, 2, 3, 4, 5))
    sent = _patch_send(monkeypatch)
    state = _State()
    state.meta.update({"broadcast.initialized": "1", "broadcast.last_id": "0"})

    asyncio.run(watcher._check_broadcast(_config(), state))

    assert len(sent) == watcher.MAX_BROADCAST_NOTICES
    assert state.meta["broadcast.last_id"] == "3"


def test_diffusion_desactivee_ne_contacte_pas_le_serveur(monkeypatch):
    calls: list[str] = []
    _patch_fetch(monkeypatch, _messages(1), calls)

    asyncio.run(watcher._check_broadcast(_config(enabled=False), _State()))

    assert calls == []


def test_une_panne_reseau_est_ignoree(monkeypatch):
    def boom(endpoint, *, timeout=None):
        raise OSError("reseau indisponible")

    monkeypatch.setattr(broadcast, "fetch_messages", boom)
    sent = _patch_send(monkeypatch)
    state = _State()
    state.meta.update({"broadcast.initialized": "1", "broadcast.last_id": "2"})

    asyncio.run(watcher._check_broadcast(_config(), state))

    assert sent == []
    assert state.meta["broadcast.last_id"] == "2"


def test_mode_once_retient_sans_notifier(monkeypatch):
    _patch_fetch(monkeypatch, _messages(4))
    sent = _patch_send(monkeypatch)
    state = _State()
    state.meta.update({"broadcast.initialized": "1", "broadcast.last_id": "2"})

    asyncio.run(watcher._check_broadcast(_config(), state, notify=False))

    assert sent == []
    assert state.meta["broadcast.last_id"] == "2"
