"""Icone de statut Linux via StatusNotifierItem.

La zone de notification de KDE et GNOME passe par D-Bus (StatusNotifierItem).
`pystray` retombe sur XEmbed et publie une icone 1x1, que Plasma etire en carre
plein. On publie donc directement un StatusNotifierItem avec un vrai pixmap et
un menu D-Bus.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from types import SimpleNamespace

logger = logging.getLogger(__name__)

try:
    from dbus_next.constants import PropertyAccess
    from dbus_next.service import (
        ServiceInterface,
        dbus_property,
        method,
        signal,
    )

    HAS_DBUS = True
except Exception:  # dependance optionnelle hors Linux
    HAS_DBUS = False
    PropertyAccess = SimpleNamespace(READ=1)

    def dbus_property(**kwargs):
        def decorate(fn):
            return fn

        return decorate

    method = dbus_property
    signal = dbus_property

    class ServiceInterface:
        def __init__(self, name: str) -> None:
            self._name = name


BUS_NAME = "org.kde.StatusNotifierItem"
WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

# Un element de menu : (libelle, action), ou None pour un separateur.
MenuItem = tuple[str, Callable[[], None]] | None


def available() -> bool:
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return False
    return HAS_DBUS


def _argb32(image) -> bytes:
    """Convertit une image RGBA en pixmap ARGB32 (ordre reseau)."""
    raw = image.tobytes()
    data = bytearray(len(raw))
    data[0::4] = raw[3::4]
    data[1::4] = raw[0::4]
    data[2::4] = raw[1::4]
    data[3::4] = raw[2::4]
    return bytes(data)


def _framed(image, size: int):
    from PIL import Image

    if image.size == (size, size):
        return image
    return image.resize((size, size), Image.LANCZOS)


def pixmaps(image, sizes: tuple[int, ...] = (64, 32)) -> list:
    """Prepare les pixmaps attendus par IconPixmap : (largeur, hauteur, ARGB32)."""
    return [[size, size, _argb32(_framed(image, size))] for size in sizes]


class _Item:
    """Etat partage entre le thread principal et la boucle D-Bus."""

    def __init__(self) -> None:
        self.title = "CheckMate"
        self.label = ""
        self.pixmaps: list = []
        self.status = "Active"

    def tooltip(self):
        return ["", [], self.title, self.label]


class MenuModel:
    """Construit l'arbre de menu D-Bus, sans dependance a la connexion."""

    def __init__(self, items: list[MenuItem]) -> None:
        self.entries: list[dict] = []
        self.actions: dict[int, Callable[[], None]] = {}
        for item in items:
            self._add(item)

    def _add(self, item: MenuItem | None) -> None:
        identifier = len(self.entries) + 1
        if item is None:
            self.entries.append({"id": identifier, "type": "separator"})
            return
        label, action = item
        self.actions[identifier] = action
        self.entries.append({"id": identifier, "type": "item", "label": label})

    def _variant(self, **props) -> dict:
        from dbus_next import Variant

        return {
            key: Variant("b" if isinstance(value, bool) else "s", value)
            for key, value in props.items()
        }

    def properties(self, entry: dict) -> dict:
        if entry["type"] == "separator":
            return self._variant(type="separator", visible=True)
        return self._variant(label=entry["label"], enabled=True, visible=True)

    def children(self) -> list:
        from dbus_next import Variant

        return [
            Variant("(ia{sv}av)", [entry["id"], self.properties(entry), []])
            for entry in self.entries
        ]

    def layout(self, parent: int, revision: int = 1) -> list:
        from dbus_next import Variant

        if parent <= 0:
            root = [
                0,
                {"children-display": Variant("s", "submenu")},
                self.children(),
            ]
        else:
            root = [parent, {}, []]
        return [revision, root]

    def group_properties(self, ids: list[int]) -> list:
        wanted = set(ids) if ids else {entry["id"] for entry in self.entries}
        return [
            [entry["id"], self.properties(entry)]
            for entry in self.entries
            if entry["id"] in wanted
        ]

    def property(self, identifier: int, name: str):
        from dbus_next import Variant

        for entry in self.entries:
            if entry["id"] == identifier:
                return self.properties(entry).get(name, Variant("s", ""))
        return Variant("s", "")

    def click(self, identifier: int) -> None:
        action = self.actions.get(identifier)
        if action is None:
            return
        try:
            action()
        except Exception as exc:
            logger.warning("action du menu echouee : %s", exc)


class _ItemService(ServiceInterface):
    def __init__(self, state: _Item, activate: Callable[[], None]) -> None:
        super().__init__(BUS_NAME)
        self._state = state
        self._activate = activate

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "ApplicationStatus"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "checkmate"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return self._state.title

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return self._state.status

    @dbus_property(access=PropertyAccess.READ)
    def WindowId(self) -> "i":
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":
        return self._state.pixmaps

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionMovieName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return self._state.tooltip()

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return MENU_PATH

    @method()
    def ContextMenu(self, x: "i", y: "i"):
        return None

    @method()
    def Activate(self, x: "i", y: "i"):
        self._activate()

    @method()
    def SecondaryActivate(self, x: "i", y: "i"):
        self._activate()

    @method()
    def Scroll(self, delta: "i", orientation: "s"):
        return None

    @signal()
    def NewIcon(self) -> "s":
        return ""

    @signal()
    def NewTitle(self) -> "s":
        return ""

    @signal()
    def NewStatus(self) -> "s":
        return self._state.status

    @signal()
    def NewToolTip(self) -> "s":
        return ""


class _MenuService(ServiceInterface):
    def __init__(self, model: MenuModel) -> None:
        super().__init__("com.canonical.dbusmenu")
        self._model = model
        self.revision = 1

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":
        return []

    @method()
    def GetLayout(self, parent: "i", depth: "i", names: "as") -> "u(ia{sv}av)":
        return self._model.layout(parent, self.revision)

    @method()
    def GetGroupProperties(self, ids: "ai", names: "as") -> "a(ia{sv})":
        return self._model.group_properties(ids)

    @method()
    def GetProperty(self, id: "i", name: "s") -> "v":
        return self._model.property(id, name)

    @method()
    def Event(self, id: "i", event: "s", data: "v", timestamp: "u"):
        if event == "clicked":
            self._model.click(id)

    @method()
    def EventGroup(self, events: "a(isvu)"):
        return None

    @method()
    def AboutToShow(self, id: "i") -> "b":
        return False

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":
        return [[], []]

    @signal()
    def LayoutUpdated(self, revision: "u", parent: "i") -> "ui":
        return [revision, parent]

    @signal()
    def ItemsPropertiesUpdated(
        self, updated: "a(ia{sv})", removed: "a(ias)"
    ) -> "a(ia{sv})a(ias)":
        return [[], []]


def _build_services(state: _Item, model: MenuModel, activate: Callable):
    return _ItemService(state, activate), _MenuService(model)


class SniTray:
    """Icone StatusNotifierItem, avec sa boucle D-Bus dans un thread dedie."""

    def __init__(
        self,
        menu_items: list[MenuItem],
        *,
        activate: Callable[[], None],
    ) -> None:
        self.state = _Item()
        self._model = MenuModel(menu_items)
        self._activate = activate
        self._reset_transport()

    def _reset_transport(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._bus = self._item = None
        self._ready = threading.Event()
        self._ok = False

    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._ok

    def _run(self) -> None:
        try:
            self._loop = self._new_loop()
            self._loop.run_until_complete(self._connect())
        except Exception as exc:
            self._unavailable(exc)
            return
        self._ok = True
        self._ready.set()
        self._serve()

    def _new_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    def _unavailable(self, exc: Exception) -> None:
        logger.warning("icone StatusNotifierItem indisponible : %s", exc)
        self._ok = False
        self._ready.set()

    def _serve(self) -> None:
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _connect(self) -> None:
        from dbus_next.aio import MessageBus

        self._bus = await MessageBus().connect()
        item, menu = _build_services(self.state, self._model, self._activate)
        self._item = item
        self._bus.export(ITEM_PATH, item)
        self._bus.export(MENU_PATH, menu)
        name = f"{BUS_NAME}-{os.getpid()}-1"
        await self._bus.request_name(name)

        introspection = await self._bus.introspect(WATCHER_NAME, WATCHER_PATH)
        proxy = self._bus.get_proxy_object(
            WATCHER_NAME, WATCHER_PATH, introspection
        )
        watcher = proxy.get_interface(WATCHER_NAME)
        await watcher.call_register_status_notifier_item(name)
        logger.info("icone StatusNotifierItem enregistree")

    def _update_state(
        self, title: str, pixmaps: list, status: str, label: str
    ) -> None:
        self.state.title = title
        self.state.label = label
        self.state.pixmaps = pixmaps
        self.state.status = status

    def update(
        self,
        title: str,
        pixmaps: list,
        status: str = "Active",
        label: str = "",
    ) -> None:
        self._update_state(title, pixmaps, status, label)
        self._schedule_updates()

    def _schedule_updates(self) -> None:
        if self._loop is None or self._item is None:
            return
        self._loop.call_soon_threadsafe(self._emit_updates)

    def _emit_updates(self) -> None:
        try:
            self._item.NewTitle()
            self._item.NewIcon()
            self._item.NewStatus()
            self._item.NewToolTip()
        except Exception:
            logger.debug("mise a jour de l'icone impossible", exc_info=True)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
