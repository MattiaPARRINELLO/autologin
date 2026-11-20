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

logger = logging.getLogger(__name__)

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
    try:
        import dbus_next  # noqa: F401
    except Exception:  # noqa: BLE001 - dependance optionnelle hors Linux
        return False
    return True


def _argb32(image) -> bytes:
    """Convertit une image RGBA en pixmap ARGB32 (ordre reseau)."""
    raw = image.tobytes()
    data = bytearray(len(raw))
    data[0::4] = raw[3::4]
    data[1::4] = raw[0::4]
    data[2::4] = raw[1::4]
    data[3::4] = raw[2::4]
    return bytes(data)


def pixmaps(image, sizes: tuple[int, ...] = (64, 32)) -> list:
    """Prepare les pixmaps attendus par IconPixmap : (largeur, hauteur, ARGB32)."""
    from PIL import Image

    result = []
    for size in sizes:
        scaled = (
            image
            if image.size == (size, size)
            else image.resize((size, size), Image.LANCZOS)
        )
        result.append([size, size, _argb32(scaled)])
    return result


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
        identifier = 0
        for item in items:
            identifier += 1
            if item is None:
                self.entries.append({"id": identifier, "type": "separator"})
                continue
            label, action = item
            self.actions[identifier] = action
            self.entries.append({"id": identifier, "type": "item", "label": label})

    def properties(self, entry: dict) -> dict:
        from dbus_next import Variant

        if entry["type"] == "separator":
            return {
                "type": Variant("s", "separator"),
                "visible": Variant("b", True),
            }
        return {
            "label": Variant("s", entry["label"]),
            "enabled": Variant("b", True),
            "visible": Variant("b", True),
        }

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
        except Exception as exc:  # noqa: BLE001
            logger.warning("action du menu echouee : %s", exc)


def _build_services(state: _Item, model: MenuModel, activate: Callable):
    from dbus_next.constants import PropertyAccess
    from dbus_next.service import ServiceInterface, dbus_property, method, signal

    class Item(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(BUS_NAME)

        @dbus_property(access=PropertyAccess.READ)
        def Category(self) -> "s":
            return "ApplicationStatus"

        @dbus_property(access=PropertyAccess.READ)
        def Id(self) -> "s":
            return "checkmate"

        @dbus_property(access=PropertyAccess.READ)
        def Title(self) -> "s":
            return state.title

        @dbus_property(access=PropertyAccess.READ)
        def Status(self) -> "s":
            return state.status

        @dbus_property(access=PropertyAccess.READ)
        def WindowId(self) -> "i":
            return 0

        @dbus_property(access=PropertyAccess.READ)
        def IconName(self) -> "s":
            return ""

        @dbus_property(access=PropertyAccess.READ)
        def IconPixmap(self) -> "a(iiay)":
            return state.pixmaps

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
            return state.tooltip()

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
            activate()

        @method()
        def SecondaryActivate(self, x: "i", y: "i"):
            activate()

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
            return state.status

        @signal()
        def NewToolTip(self) -> "s":
            return ""

    class Menu(ServiceInterface):
        def __init__(self) -> None:
            super().__init__("com.canonical.dbusmenu")
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
            return model.layout(parent, self.revision)

        @method()
        def GetGroupProperties(self, ids: "ai", names: "as") -> "a(ia{sv})":
            return model.group_properties(ids)

        @method()
        def GetProperty(self, id: "i", name: "s") -> "v":
            return model.property(id, name)

        @method()
        def Event(self, id: "i", event: "s", data: "v", timestamp: "u"):
            if event == "clicked":
                model.click(id)

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

    return Item(), Menu()


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
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._bus = None
        self._item = None
        self._ready = threading.Event()
        self._ok = False

    def start(self, timeout: float = 5.0) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._ok

    def _run(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._connect())
        except Exception as exc:  # noqa: BLE001
            logger.warning("icone StatusNotifierItem indisponible : %s", exc)
            self._ok = False
            self._ready.set()
            return
        self._ok = True
        self._ready.set()
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
        proxy = self._bus.get_proxy_object(WATCHER_NAME, WATCHER_PATH, introspection)
        watcher = proxy.get_interface(WATCHER_NAME)
        await watcher.call_register_status_notifier_item(name)
        logger.info("icone StatusNotifierItem enregistree")

    def update(
        self, title: str, pixmaps: list, status: str = "Active", label: str = ""
    ) -> None:
        self.state.title = title
        self.state.label = label
        self.state.pixmaps = pixmaps
        self.state.status = status
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
