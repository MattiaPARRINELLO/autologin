"""Point d'entree en ligne de commande."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import BUILD, __version__
from .autostart import (
    UNIT_NAME,
    autostart_enabled,
    current_executable,
    disable_autostart,
    enable_autostart,
)
from .browser import (
    bundled_browser_present,
    missing_browser_message,
    resolve_launch_options,
)
from .config import Config, ConfigError, load_config
from .credentials import (
    get_password,
    keyring_available,
    set_password,
)
from .logging_setup import setup_logging
from .notifications import Notifier
from .paths import default_config_path, default_log_file
from .self_update import update_now
from .setup_server import run_setup
from .signature import SignatureError, load_signature, parse_points, save_signature
from .state import StateStore
from .status_server import read_runtime, status_alive
from .support import build_support_bundle
from .updates import UpdateError, check_for_update, fetch_releases
from .watcher import run_loop
from .window import open_url

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = str(default_config_path())

CAPTURE_HTML = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>CheckMate - capture de signature</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0f172a; color: #e2e8f0; font-family: system-ui, sans-serif; }
  .card { background: #1e293b; padding: 28px; border-radius: 18px; box-shadow: 0 20px 60px rgba(0,0,0,.45); }
  h1 { margin: 0 0 6px; font-size: 20px; }
  p { margin: 0 0 18px; color: #94a3b8; font-size: 14px; }
  canvas { background: #fff; border-radius: 12px; cursor: crosshair; touch-action: none; display: block; }
  .actions { display: flex; gap: 12px; margin-top: 16px; }
  button { flex: 1; padding: 12px; border-radius: 10px; border: 0; font-weight: 700; cursor: pointer; font-size: 15px; }
  #save { background: #22c55e; color: #04220f; }
  #clear { background: #334155; color: #e2e8f0; }
</style>
</head>
<body>
  <div class="card">
    <h1>Dessine ta signature</h1>
    <p>Trace la signature a la souris, puis clique sur Enregistrer.</p>
    <canvas id="pad" width="640" height="320"></canvas>
    <p id="message" role="status"></p>
    <div class="actions">
      <button id="clear" type="button">Effacer</button>
      <button id="save" type="button">Enregistrer</button>
    </div>
  </div>
<script>
  const canvas = document.getElementById('pad');
  const ctx = canvas.getContext('2d');
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#0f172a';

  const state = { points: [], done: false };
  window.__signatureCapture = state;
  let drawing = false;

  function position(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height)
    };
  }

  canvas.addEventListener('pointerdown', (event) => {
    drawing = true;
    canvas.setPointerCapture(event.pointerId);
    const point = position(event);
    state.points.push({ x: point.x, y: point.y, type: 'start' });
    ctx.beginPath();
    ctx.moveTo(point.x, point.y);
  });

  canvas.addEventListener('pointermove', (event) => {
    if (!drawing) return;
    const point = position(event);
    state.points.push({ x: point.x, y: point.y, type: 'move' });
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
  });

  function endStroke(event) {
    if (!drawing) return;
    drawing = false;
    const point = position(event);
    state.points.push({ x: point.x, y: point.y, type: 'end' });
    ctx.stroke();
  }
  canvas.addEventListener('pointerup', endStroke);
  canvas.addEventListener('pointercancel', endStroke);

  function pointsExtent(points) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const point of points) {
      if (point.x < minX) minX = point.x;
      if (point.y < minY) minY = point.y;
      if (point.x > maxX) maxX = point.x;
      if (point.y > maxY) maxY = point.y;
    }
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) return 0;
    return Math.max(maxX - minX, maxY - minY);
  }

  document.getElementById('clear').addEventListener('click', () => {
    state.points.length = 0;
    document.getElementById('message').textContent = '';
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  document.getElementById('save').addEventListener('click', () => {
    if (state.points.length < 2 || pointsExtent(state.points) < 2) {
      document.getElementById('message').textContent =
        'Dessine une vraie signature : un clic ne suffit pas.';
      return;
    }
    state.done = true;
  });
</script>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="checkmate-watcher",
        description="Surveille CESAR Emineo et propose de signer l'emargement.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=[
            "run",
            "capture",
            "test-notification",
            "check-config",
            "reset-state",
            "self-test",
            "set-password",
            "install-autostart",
            "uninstall-autostart",
            "setup",
            "support-bundle",
            "import-signature",
            "check-update",
            "update",
            "stats",
            "status",
        ],
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG, help="chemin du fichier TOML"
    )
    parser.add_argument("--once", action="store_true", help="un seul cycle puis sortie")
    parser.add_argument(
        "--dry-run", action="store_true", help="detecte sans notifier ni signer"
    )
    parser.add_argument("--auto", action="store_true", help="signe sans confirmation")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="update : installer sans demander de confirmation",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="update : verifier seulement, sans installer",
    )
    parser.add_argument("--output", help="support-bundle : chemin de l'archive")
    parser.add_argument("--file", help="import-signature : fichier JSON")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="setup : ne pas ouvrir le navigateur automatiquement",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="self-test : envoie aussi une notification reelle",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} (build {BUILD})",
    )
    return parser


def _mask(value: str) -> str:
    if not value:
        return "(vide)"
    return "*" * min(len(value), 8) + f" ({len(value)} caracteres)"


def command_check_config(config: Config) -> int:
    print(f"CheckMate {__version__} (build {BUILD})")
    print("Configuration chargee")
    print(f"  CESAR          : {config.cesar.base_url}")
    print(f"  Utilisateur    : {config.cesar.username}")
    print(f"  Mot de passe   : {_mask(config.cesar.password)}")
    print(f"  Intervalle     : {config.watcher.poll_interval}s")
    print(f"  Deduplication  : {config.watcher.dedupe_ttl}s")
    print(f"  Confirmation   : {config.watcher.confirm_timeout}s")
    print(f"  Nouvelle demande : {config.watcher.prompt_retry}s")
    print(f"  Auto-signature : {config.watcher.auto_sign}")
    print(f"  Visible a la signature : {config.watcher.visible_on_sign}")
    print(f"  Plages         : {config.schedule.describe()}")
    print(f"  Profil         : {config.watcher.profile_dir}")
    print(f"  Etat           : {config.watcher.state_file}")
    print(f"  Signature      : {config.signature.file}")
    print(f"  Logs           : {default_log_file()}")

    if config.signature.file.is_file():
        try:
            points = load_signature(config.signature.file)
        except SignatureError as exc:
            print(f"  Signature      : INVALIDE ({exc})")
        else:
            print(f"  Signature      : OK ({len(points)} points)")
    else:
        print("  Signature      : ABSENTE, lance 'capture'")

    for tool in ("notify-send", "zenity"):
        found = shutil.which(tool)
        print(f"  Outil {tool:<10}: {found or 'INTROUVABLE'}")
    return 0


async def command_capture(config: Config) -> int:
    from playwright.async_api import async_playwright

    print("Ouverture de la fenetre de capture...")
    async with async_playwright() as playwright:
        options = resolve_launch_options(
            playwright.chromium, config.watcher.executable_path
        ).as_kwargs()
        try:
            browser = await playwright.chromium.launch(headless=False, **options)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                print(missing_browser_message())
                return 1
            raise
        page = await browser.new_page(viewport={"width": 900, "height": 640})
        await page.set_content(CAPTURE_HTML)
        try:
            await page.wait_for_function(
                "window.__signatureCapture && window.__signatureCapture.done === true",
                timeout=300_000,
            )
            raw = await page.evaluate("window.__signatureCapture.points")
        except Exception as exc:
            await browser.close()
            print(f"Capture annulee : {exc}")
            return 1
        await browser.close()

    try:
        points = parse_points(raw)
    except SignatureError as exc:
        print(f"Signature invalide : {exc}")
        return 1

    save_signature(config.signature.file, points)
    print(f"Signature enregistree ({len(points)} points) dans {config.signature.file}")
    return 0


def command_test_notification(config: Config) -> int:
    notifier = Notifier.from_config(config)
    sent = notifier.send(
        "CheckMate",
        "Ceci est une notification de test.",
        urgency="normal",
    )
    print("notification envoyee" if sent else "notification impossible")
    answer = notifier.ask(
        "Ceci est une confirmation de test. Clique sur un bouton.",
        timeout=60,
        title=config.notifications.app_name,
    )
    print(f"reponse : {answer}")
    return 0 if sent else 1


def command_set_password(config: Config) -> int:
    password = getpass.getpass("Mot de passe CESAR : ")
    if not password:
        print("mot de passe vide, rien n'a ete enregistre")
        return 1
    if not keyring_available():
        print("trousseau systeme indisponible : utilise password_env ou password")
        return 1
    if not set_password(config.cesar.keyring_service, config.cesar.username, password):
        print("enregistrement dans le trousseau impossible")
        return 1
    print(f"mot de passe enregistre dans le trousseau ({config.cesar.keyring_service})")
    return 0


def command_self_test(config: Config, *, notify: bool = False) -> int:
    checks: list[tuple[str, bool, str]] = []

    if config.cesar.password:
        checks.append(("mot de passe", True, "disponible"))
    else:
        checks.append(("mot de passe", False, "absent"))

    try:
        points = load_signature(config.signature.file)
    except SignatureError as exc:
        checks.append(("signature", False, str(exc)))
    else:
        checks.append(("signature", True, f"{len(points)} points"))

    class Probe:
        executable_path = ""

    options = resolve_launch_options(Probe(), config.watcher.executable_path)
    if options.executable_path:
        checks.append(("navigateur", True, options.executable_path))
    elif options.channel:
        checks.append(("navigateur", True, f"canal {options.channel}"))
    elif bundled_browser_present():
        checks.append(("navigateur", True, "Chromium Playwright"))
    else:
        checks.append(("navigateur", False, "aucun navigateur trouve"))

    if keyring_available():
        stored = get_password(config.cesar.keyring_service, config.cesar.username)
        checks.append(
            ("trousseau", True, "mot de passe present" if stored else "disponible")
        )
    else:
        checks.append(("trousseau", False, "indisponible"))

    if autostart_enabled():
        checks.append(("demarrage auto", True, "actif"))
    else:
        checks.append(("demarrage auto", False, "inactif"))

    if config.schedule.enabled:
        checks.append(("planning", True, config.schedule.describe()))
    else:
        checks.append(("planning", False, "desactive"))

    log_dir = config.watcher.state_file.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".checkmate-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        checks.append(("dossier de donnees", False, str(exc)))
    else:
        checks.append(("dossier de donnees", True, str(log_dir)))

    if notify:
        notifier = Notifier.from_config(config)
        sent = notifier.send(
            "CheckMate",
            "Test de notification reussi.",
            urgency="normal",
        )
        checks.append(("notification", sent, "envoyee" if sent else "echec"))

    print("Bilan CheckMate")
    failures = 0
    for name, ok, detail in checks:
        if not ok:
            failures += 1
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] {name:<16} {detail}")

    return 0 if failures == 0 else 1


def command_support_bundle(
    config: Config, config_path: Path, output: str | None
) -> int:
    target = build_support_bundle(
        config,
        config_path,
        Path(output).expanduser() if output else None,
    )
    print(f"archive creee : {target}")
    print("elle ne contient ni mot de passe ni signature")
    return 0


def command_import_signature(config: Config, file_path: str | None) -> int:
    if not file_path:
        print("indique un fichier avec --file")
        return 1
    path = Path(file_path).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        points = parse_points(data)
    except (OSError, json.JSONDecodeError, SignatureError) as exc:
        print(f"import impossible : {exc}")
        return 1
    save_signature(config.signature.file, points)
    print(f"signature importee ({len(points)} points) dans {config.signature.file}")
    return 0


def command_status(config: Config, config_path: Path) -> int:
    runtime = read_runtime()
    if runtime and status_alive(runtime):
        open_url(str(runtime["url"]))
        return 0

    executable = current_executable()
    command = [str(executable), "--config", str(config_path), "run"]
    if sys.platform.startswith("win"):
        subprocess.Popen(command, close_fds=True, creationflags=0x00000008)
    else:
        systemctl = shutil.which("systemctl")
        started = False
        if systemctl:
            result = subprocess.run(
                [systemctl, "--user", "start", UNIT_NAME],
                check=False,
                capture_output=True,
                timeout=20,
            )
            started = result.returncode == 0
        if not started:
            subprocess.Popen(command, close_fds=True, start_new_session=True)

    for _ in range(40):
        runtime = read_runtime()
        if runtime and status_alive(runtime):
            open_url(str(runtime["url"]))
            return 0
        time.sleep(0.5)
    print("CheckMate n'a pas demarre. Consulte les logs.")
    return 1


def command_stats(config: Config) -> int:
    state = StateStore(config.watcher.state_file)
    print(f"CheckMate {__version__} (build {BUILD})")
    print("Statistiques locales")
    print(f"  Demarrages        : {state.counter('stats.starts')}")
    print(f"  Detections        : {state.counter('stats.detections')}")
    print(f"  Signatures        : {state.counter('stats.signed')}")
    print(f"  Erreurs           : {state.counter('stats.errors')}")
    try:
        releases = fetch_releases()
    except Exception as exc:
        print(f"  Telechargements   : indisponibles ({exc})")
        return 0
    downloads = sum(release.downloads for release in releases)
    print(f"  Telechargements   : {downloads} (artefacts GitHub)")
    if releases:
        latest = max(releases, key=lambda release: release.version)
        print(f"  Derniere version  : {latest.tag}")
    return 0


def command_check_update(config: Config) -> int:
    try:
        release = check_for_update(
            __version__,
            channel=config.updates.channel,
        )
    except Exception as exc:
        print(f"verification impossible : {exc}")
        return 1
    if release is None:
        print(f"CheckMate {__version__} est a jour (canal {config.updates.channel})")
        return 0
    print(f"Mise a jour disponible : {release.tag} (canal {config.updates.channel})")
    print(release.url)
    return 0


def command_update(config: Config, *, check_only: bool, assume_yes: bool) -> int:
    try:
        release = check_for_update(
            __version__,
            channel=config.updates.channel,
        )
    except Exception as exc:
        print(f"verification impossible : {exc}")
        return 1
    if release is None:
        print(f"CheckMate {__version__} est a jour (canal {config.updates.channel})")
        return 0
    print(f"Mise a jour disponible : {release.tag} (canal {config.updates.channel})")
    if check_only:
        print(release.url)
        return 0
    if not assume_yes:
        try:
            answer = input("Installer maintenant ? [o/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"o", "oui", "y", "yes"}:
            print("Annule")
            return 1
    print("Telechargement et verification de la somme...")
    try:
        version = update_now(config)
    except UpdateError as exc:
        print(f"mise a jour impossible : {exc}")
        return 1
    print(f"Installation de {version} en cours. CheckMate redemarre.")
    return 0


def command_install_autostart(config_path: Path) -> int:
    executable = current_executable()
    config_path = config_path.expanduser().resolve()
    if not enable_autostart(executable, config_path):
        print("installation du demarrage automatique impossible")
        return 1
    print(f"demarrage automatique installe : {executable} --config {config_path} run")
    return 0


def command_uninstall_autostart() -> int:
    if not disable_autostart():
        print("desinstallation du demarrage automatique impossible")
        return 1
    print("demarrage automatique desactive")
    return 0


def _ensure_console_streams() -> None:
    """En mode fenetre (PyInstaller windowed), stdout et stderr valent None."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def main(argv: list[str] | None = None) -> int:
    _ensure_console_streams()
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    if args.command == "setup":
        return run_setup(
            Path(args.config).expanduser(),
            open_browser=not args.no_browser,
        )

    needs_password = args.command in {"run", "capture", "test-notification"}
    try:
        config = load_config(Path(args.config), require_password=needs_password)
    except ConfigError as exc:
        logger.error("configuration invalide : %s", exc)
        return 2

    if args.command == "set-password":
        return command_set_password(config)
    if args.command == "self-test":
        return command_self_test(config, notify=args.notify)
    if args.command == "install-autostart":
        return command_install_autostart(Path(args.config))
    if args.command == "uninstall-autostart":
        return command_uninstall_autostart()
    if args.command == "support-bundle":
        return command_support_bundle(
            config, Path(args.config).expanduser(), args.output
        )
    if args.command == "import-signature":
        return command_import_signature(config, args.file)
    if args.command == "check-update":
        return command_check_update(config)
    if args.command == "update":
        return command_update(config, check_only=args.check, assume_yes=args.yes)
    if args.command == "stats":
        return command_stats(config)
    if args.command == "status":
        return command_status(config, Path(args.config).expanduser())
    if args.command == "check-config":
        return command_check_config(config)
    if args.command == "test-notification":
        return command_test_notification(config)
    if args.command == "reset-state":
        path = config.watcher.state_file
        if path.is_file():
            path.unlink()
            print(f"Etat reinitialise : {path}")
        else:
            print(f"Aucun etat a supprimer : {path}")
        return 0
    if args.command == "capture":
        return asyncio.run(command_capture(config))

    try:
        return asyncio.run(
            run_loop(
                config,
                once=args.once,
                dry_run=args.dry_run,
                auto_override=True if args.auto else None,
                config_path=Path(args.config).expanduser(),
            )
        )
    except KeyboardInterrupt:
        logger.info("arret demande")
        return 130


if __name__ == "__main__":
    sys.exit(main())
