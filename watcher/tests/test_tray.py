from __future__ import annotations

import pytest

from checkmate_watcher import tray


def test_le_callback_expose_deux_arguments():
    handler = tray.menu_handler(lambda: None)

    assert handler.__code__.co_argcount == 2


def test_le_callback_appelle_l_action():
    calls: list[str] = []

    handler = tray.menu_handler(lambda: calls.append("ok"))
    handler("icone", "item")

    assert calls == ["ok"]


@pytest.mark.skipif(tray.pystray is None, reason="pystray indisponible")
def test_pystray_accepte_le_callback():
    item = tray.pystray.MenuItem("Test", tray.menu_handler(lambda: None))

    assert item.text == "Test"
