from __future__ import annotations

from checkmate_watcher.cesar import is_success_confirmation, signal_key
from checkmate_watcher.state import StateStore


def test_signal_key_est_stable_et_sensible_au_cours():
    payload = {"action": "1234", "row": "Maths 10h", "label": "Signer"}
    assert signal_key(payload) == signal_key(dict(payload))
    autre = {"action": "5678", "row": "Maths 10h", "label": "Signer"}
    assert signal_key(payload) != signal_key(autre)


def test_signal_key_ignore_les_espaces_superflus():
    a = {"action": "", "row": "Maths   10h", "label": " Signer "}
    b = {"action": "", "row": "Maths 10h", "label": "Signer"}
    assert signal_key(a) == signal_key(b)


def test_is_success_confirmation():
    assert is_success_confirmation("Votre presence a bien ete prise en compte")
    assert is_success_confirmation("Présence enregistrée")
    assert not is_success_confirmation("Une erreur est survenue")


def test_state_deduplique_puis_expire(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path, ttl=60)
    assert not store.seen("abc", now=1000)
    store.mark("abc", now=1000)
    assert store.seen("abc", now=1030)
    assert not store.seen("abc", now=1061)

    reloaded = StateStore(path, ttl=60)
    assert reloaded.seen("abc", now=1030)


def test_state_memorise_une_meta(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path, ttl=60)
    store.set_meta("update_notified", "watcher-v0.2.0")
    assert store.get_meta("update_notified") == "watcher-v0.2.0"

    reloaded = StateStore(path, ttl=60)
    assert reloaded.get_meta("update_notified") == "watcher-v0.2.0"


def test_state_compteurs(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path, ttl=60)
    assert store.counter("stats.starts") == 0
    store.increment("stats.starts")
    store.increment("stats.starts", 2)
    assert store.counter("stats.starts") == 3

    reloaded = StateStore(path, ttl=60)
    assert reloaded.counter("stats.starts") == 3


def test_state_ignore_un_fichier_corrompu(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("pas du json", encoding="utf-8")
    store = StateStore(path, ttl=60)
    assert not store.seen("abc")
    store.mark("abc")
    assert path.is_file()
