from __future__ import annotations

import pytest
from PIL import Image

from checkmate_watcher import sni

dbus_next = pytest.importorskip("dbus_next")


def test_available_sans_bus(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    assert sni.available() is False


def test_pixmaps_contiennent_une_image():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    image.paste((47, 111, 79, 255), (8, 8, 56, 56))
    result = sni.pixmaps(image)
    assert [entry[0] for entry in result] == [64, 32]
    width, height, data = result[0]
    assert (width, height) == (64, 64)
    assert len(data) == 64 * 64 * 4
    assert sum(1 for alpha in data[0::4] if alpha) > 0


def test_argb32_ordre_des_canaux():
    image = Image.new("RGBA", (1, 1), (10, 20, 30, 40))
    assert sni._argb32(image) == bytes((40, 10, 20, 30))


def test_menu_modele_structure():
    model = sni.MenuModel([("Ouvrir", lambda: None), None, ("Quitter", lambda: None)])
    revision, layout = model.layout(0)
    assert revision == 1
    root_id, root_properties, children = layout
    assert root_id == 0
    assert "children-display" in root_properties
    labels = [child.value[1]["label"].value for child in children[:1]]
    assert labels == ["Ouvrir"]
    assert children[1].value[1]["type"].value == "separator"
    assert children[2].value[1]["label"].value == "Quitter"


def test_menu_modele_marshalling():
    from dbus_next._private.marshaller import Marshaller

    model = sni.MenuModel([("Ouvrir", lambda: None), None, ("Quitter", lambda: None)])
    revision, layout = model.layout(0)
    Marshaller("u(ia{sv}av)", [revision, layout])
    Marshaller("a(ia{sv})", [model.group_properties([])])


def test_menu_modele_clic():
    calls: list[str] = []
    model = sni.MenuModel([("Ouvrir", lambda: calls.append("ouvrir")), None])
    model.click(1)
    model.click(2)
    model.click(99)
    assert calls == ["ouvrir"]


def test_menu_modele_clic_en_erreur(caplog):
    def boom() -> None:
        raise RuntimeError("echec")

    model = sni.MenuModel([("Casser", boom)])
    model.click(1)
    assert "action du menu echouee" in caplog.text


def test_menu_modele_parent_inconnu():
    model = sni.MenuModel([])
    revision, layout = model.layout(7)
    assert revision == 1
    assert layout == [7, {}, []]


def test_niveau_de_gravite():
    from checkmate_watcher.tray import status_level

    assert status_level("error") == "NeedsAttention"
    assert status_level("active") == "Active"
    assert status_level("outside") == "Active"
