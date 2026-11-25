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
from .signature import (
    SignatureError,
    load_signature,
    parse_points,
    save_signature,
)
from .state import StateStore
from .status_server import read_runtime, status_alive
from .support import build_support_bundle
from .updates import UpdateError, fetch_releases, update_policy
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
         background: #0f172a; color: #e2e8f0;
         font-family: system-ui, sans-serif; }
  .card { background: #1e293b; padding: 28px; border-radius: 18px;
    box-shadow: 0 20px 60px rgba(0,0,0,.45); }
  h1 { margin: 0 0 6px; font-size: 20px; }
  p { margin: 0 0 18px; color: #94a3b8; font-size: 14px; }
  canvas { background: #fff; border-radius: 12px; cursor: crosshair;
    touch-action: none; display: block; }
  .actions { display: flex; gap: 12px; margin-top: 16px; }
  button { flex: 1; padding: 12px; border-radius: 10px; border: 0;
    font-weight: 700; cursor: pointer; font-size: 15px; }
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


HELP_NO_BROWSER = "setup : ne pas ouvrir le navigateur automatiquement"
DRY_RUN_HELP = "detecte sans notifier ni signer"
HELP_NOTIFY = "self-test : envoie aussi une notification reelle"

COMMANDS = (
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
)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("command", nargs="?", default="run", choices=COMMANDS)
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG, help="chemin du fichier TOML"
    )


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--once", action="store_true", help="un seul cycle puis sortie"
    )
    parser.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    parser.add_argument(
        "--auto", action="store_true", help="signe sans confirmation"
    )


def _add_update_args(parser: argparse.ArgumentParser) -> None:
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


def _add_command_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output", help="support-bundle : chemin de l'archive"
    )
    parser.add_argument("--file", help="import-signature : fichier JSON")
    parser.add_argument(
        "--no-browser", action="store_true", help=HELP_NO_BROWSER
    )
    parser.add_argument("--notify", action="store_true", help=HELP_NOTIFY)


def _add_meta_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} (build {BUILD})",
    )


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="checkmate-watcher",
        description=(
            "Surveille CESAR Emineo et propose de signer l'emargement."
        ),
    )


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    _add_common_args(parser)
    _add_run_args(parser)
    _add_update_args(parser)
    _add_command_args(parser)
    _add_meta_args(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = _build_parser()
    _configure_parser(parser)
    return parser


def _mask(value: str) -> str:
    if not value:
        return "(vide)"
    return "*" * min(len(value), 8) + f" ({len(value)} caracteres)"


def _afficher_identite(config: Config) -> None:
    print(f"CheckMate {__version__} (build {BUILD})")
    print("Configuration chargee")
    print(f"  CESAR          : {config.cesar.base_url}")
    print(f"  Utilisateur    : {config.cesar.username}")
    print(f"  Mot de passe   : {_mask(config.cesar.password)}")


def _afficher_watcher(config: Config) -> None:
    print(f"  Intervalle     : {config.watcher.poll_interval}s")
    print(f"  Deduplication  : {config.watcher.dedupe_ttl}s")
    print(f"  Confirmation   : {config.watcher.confirm_timeout}s")
    print(f"  Nouvelle demande : {config.watcher.prompt_retry}s")
    print(f"  Transport      : {config.watcher.transport}")
    print(f"  Auto-signature : {config.watcher.auto_sign}")
    print(f"  Visible a la signature : {config.watcher.visible_on_sign}")
    print(f"  Plages         : {config.schedule.describe()}")


def _afficher_chemins(config: Config) -> None:
    print(f"  Profil         : {config.watcher.profile_dir}")
    print(f"  Etat           : {config.watcher.state_file}")
    print(f"  Signature      : {config.signature.file}")
    print(f"  Logs           : {default_log_file()}")


def _afficher_signature(statut: tuple[str, object]) -> None:
    status, detail = statut
    if status == "ok":
        print(f"  Signature      : OK ({detail} points)")
        return
    if status == "invalid":
        print(f"  Signature      : INVALIDE ({detail})")
        return
    print("  Signature      : ABSENTE, lance 'capture'")


def _afficher_outils(outils: list[tuple[str, str | None]]) -> None:
    for tool, found in outils:
        print(f"  Outil {tool:<10}: {found or 'INTROUVABLE'}")


def _afficher_check_config(
    config: Config,
    signature_status: tuple[str, object],
    tools_status: list[tuple[str, str | None]],
) -> None:
    _afficher_identite(config)
    _afficher_watcher(config)
    _afficher_chemins(config)
    _afficher_signature(signature_status)
    _afficher_outils(tools_status)


def _statut_signature(fichier: Path) -> tuple[str, object]:
    if not fichier.is_file():
        return ("absent", None)
    try:
        return ("ok", len(load_signature(fichier)))
    except SignatureError as exc:
        return ("invalid", exc)


def command_check_config(config: Config) -> int:
    statut = _statut_signature(config.signature.file)
    tools_status = [
        (tool, shutil.which(tool)) for tool in ("notify-send", "zenity")
    ]
    _afficher_check_config(config, statut, tools_status)
    return 0


async def command_capture(config: Config) -> int:
    from playwright.async_api import async_playwright

    print("Ouverture de la fenetre de capture...")
    async with async_playwright() as playwright:
        options = resolve_launch_options(
            playwright.chromium, config.watcher.executable_path
        ).as_kwargs()
        try:
            browser = await playwright.chromium.launch(
                headless=False, **options
            )
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                print(missing_browser_message())
                return 1
            raise
        page = await browser.new_page(viewport={"width": 900, "height": 640})
        await page.set_content(CAPTURE_HTML)
        try:
            await page.wait_for_function(
                "window.__signatureCapture && "
                "window.__signatureCapture.done === true",
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
    print(
        f"Signature enregistree ({len(points)} points) "
        f"dans {config.signature.file}"
    )
    return 0


def _afficher_test_notification(sent: bool, answer: object) -> None:
    print("notification envoyee" if sent else "notification impossible")
    print(f"reponse : {answer}")


def _envoyer_test(notifier: Notifier) -> bool:
    return notifier.send(
        "CheckMate",
        "Ceci est une notification de test.",
        urgency="normal",
    )


def _demander_test(notifier: Notifier, config: Config) -> object:
    return notifier.ask(
        "Ceci est une confirmation de test. Clique sur un bouton.",
        timeout=60,
        title=config.notifications.app_name,
    )


def command_test_notification(config: Config) -> int:
    notifier = Notifier.from_config(config)
    sent = _envoyer_test(notifier)
    answer = _demander_test(notifier, config)
    _afficher_test_notification(sent, answer)
    return 0 if sent else 1


def _afficher_set_password(etape: str, service: str = "") -> None:
    if etape == "vide":
        print("mot de passe vide, rien n'a ete enregistre")
    elif etape == "pas_trousseau":
        print(
            "trousseau systeme indisponible : utilise password_env ou password"
        )
    elif etape == "echec":
        print("enregistrement dans le trousseau impossible")
    else:
        print(f"mot de passe enregistre dans le trousseau ({service})")


def _enregistrer_set_password(config: Config, password: str) -> int:
    cesar = config.cesar
    etape = "ok"
    if not password:
        etape = "vide"
    elif not keyring_available():
        etape = "pas_trousseau"
    elif not set_password(cesar.keyring_service, cesar.username, password):
        etape = "echec"
    _afficher_set_password(etape, cesar.keyring_service)
    return 0 if etape == "ok" else 1


def command_set_password(config: Config) -> int:
    return _enregistrer_set_password(
        config, getpass.getpass("Mot de passe CESAR : ")
    )


def _afficher_self_test(checks: list[tuple[str, bool, str]]) -> None:
    print("Bilan CheckMate")
    for name, ok, detail in checks:
        marker = "OK  " if ok else "FAIL"
        print(f"  [{marker}] {name:<16} {detail}")


def _check_password(config: Config) -> tuple[str, bool, str]:
    if config.cesar.password:
        return ("mot de passe", True, "disponible")
    return ("mot de passe", False, "absent")


def _check_signature(config: Config) -> tuple[str, bool, str]:
    try:
        points = load_signature(config.signature.file)
    except SignatureError as exc:
        return ("signature", False, str(exc))
    return ("signature", True, f"{len(points)} points")


def _check_browser(config: Config) -> tuple[str, bool, str]:
    class Probe:
        executable_path = ""

    options = resolve_launch_options(Probe(), config.watcher.executable_path)
    if options.executable_path:
        return ("navigateur", True, options.executable_path)
    if options.channel:
        return ("navigateur", True, f"canal {options.channel}")
    if bundled_browser_present():
        return ("navigateur", True, "Chromium Playwright")
    return ("navigateur", False, "aucun navigateur trouve")


def _check_keyring(config: Config) -> tuple[str, bool, str]:
    if not keyring_available():
        return ("trousseau", False, "indisponible")
    stored = get_password(config.cesar.keyring_service, config.cesar.username)
    detail = "mot de passe present" if stored else "disponible"
    return ("trousseau", True, detail)


def _check_autostart() -> tuple[str, bool, str]:
    if autostart_enabled():
        return ("demarrage auto", True, "actif")
    return ("demarrage auto", False, "inactif")


def _check_schedule(config: Config) -> tuple[str, bool, str]:
    if config.schedule.enabled:
        return ("planning", True, config.schedule.describe())
    return ("planning", False, "desactive")


def _check_data_dir(config: Config) -> tuple[str, bool, str]:
    log_dir = config.watcher.state_file.parent
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".checkmate-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return ("dossier de donnees", False, str(exc))
    return ("dossier de donnees", True, str(log_dir))


def _check_notification(config: Config) -> tuple[str, bool, str]:
    notifier = Notifier.from_config(config)
    sent = notifier.send("CheckMate", "Test de notification reussi.", "normal")
    return ("notification", sent, "envoyee" if sent else "echec")


def _checks_base(config: Config) -> list:
    return [
        _check_password(config),
        _check_signature(config),
        _check_browser(config),
        _check_keyring(config),
        _check_autostart(),
        _check_schedule(config),
        _check_data_dir(config),
    ]


def _collecter_checks(config: Config, notify: bool) -> list:
    checks = _checks_base(config)
    if notify:
        checks.append(_check_notification(config))
    return checks


def command_self_test(config: Config, *, notify: bool = False) -> int:
    checks = _collecter_checks(config, notify)
    failures = sum(1 for _name, ok, _detail in checks if not ok)
    _afficher_self_test(checks)
    return 0 if failures == 0 else 1


def _afficher_support_bundle(target: Path) -> None:
    print(f"archive creee : {target}")
    print("elle ne contient ni mot de passe ni signature")


def command_support_bundle(
    config: Config, config_path: Path, output: str | None
) -> int:
    target = build_support_bundle(
        config,
        config_path,
        Path(output).expanduser() if output else None,
    )
    _afficher_support_bundle(target)
    return 0


def _message_import(
    *,
    manquant: bool = False,
    erreur: object = None,
    points: int | None = None,
    fichier: Path | None = None,
) -> str:
    if manquant:
        return "indique un fichier avec --file"
    if erreur is not None:
        return f"import impossible : {erreur}"
    return f"signature importee ({points} points) dans {fichier}"


def _afficher_import_signature(**options: object) -> None:
    print(_message_import(**options))


def _charger_points_signature(path: Path) -> tuple[list | None, object | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return parse_points(data), None
    except (OSError, json.JSONDecodeError, SignatureError) as exc:
        return None, exc


def _enregistrer_points_import(config: Config, points: list) -> None:
    save_signature(config.signature.file, points)
    _afficher_import_signature(
        points=len(points), fichier=config.signature.file
    )


def command_import_signature(config: Config, file_path: str | None) -> int:
    if not file_path:
        _afficher_import_signature(manquant=True)
        return 1
    points, erreur = _charger_points_signature(Path(file_path).expanduser())
    if erreur:
        _afficher_import_signature(erreur=erreur)
        return 1
    _enregistrer_points_import(config, points)
    return 0


def _afficher_status_demarrage_echec() -> None:
    print("CheckMate n'a pas demarre. Consulte les logs.")


def _ouvrir_si_pret() -> bool:
    runtime = read_runtime()
    if runtime and status_alive(runtime):
        open_url(str(runtime["url"]))
        return True
    return False


def _lancer_systemd() -> bool:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False
    cmd = [systemctl, "--user", "start", UNIT_NAME]
    lance = subprocess.run(cmd, check=False, capture_output=True, timeout=20)
    return lance.returncode == 0


def _demarrer(config_path: Path) -> None:
    command = [str(current_executable()), "--config", str(config_path), "run"]
    if sys.platform.startswith("win"):
        subprocess.Popen(command, close_fds=True, creationflags=0x00000008)
        return
    if _lancer_systemd():
        return
    subprocess.Popen(command, close_fds=True, start_new_session=True)


def _attendre_runtime(tentatives: int = 40) -> bool:
    for _ in range(tentatives):
        if _ouvrir_si_pret():
            return True
        time.sleep(0.5)
    return False


def command_status(config: Config, config_path: Path) -> int:
    if _ouvrir_si_pret():
        return 0
    _demarrer(config_path)
    if _attendre_runtime():
        return 0
    _afficher_status_demarrage_echec()
    return 1


def _afficher_compteurs(
    starts: int, detections: int, signed: int, errors: int
) -> None:
    print(f"  Demarrages        : {starts}")
    print(f"  Detections        : {detections}")
    print(f"  Signatures        : {signed}")
    print(f"  Erreurs           : {errors}")


def _afficher_telechargements(
    downloads: int | None, latest_tag: str | None, erreur: object
) -> None:
    if erreur is not None:
        print(f"  Telechargements   : indisponibles ({erreur})")
        return
    print(f"  Telechargements   : {downloads} (artefacts GitHub)")
    if latest_tag is not None:
        print(f"  Derniere version  : {latest_tag}")


def _afficher_stats(
    starts, detections, signed, errors, downloads, latest_tag, erreur=None
):
    print(f"CheckMate {__version__} (build {BUILD})")
    print("Statistiques locales")
    _afficher_compteurs(starts, detections, signed, errors)
    _afficher_telechargements(downloads, latest_tag, erreur)


def _lire_compteurs(state: StateStore) -> tuple[int, int, int, int]:
    return (
        state.counter("stats.starts"),
        state.counter("stats.detections"),
        state.counter("stats.signed"),
        state.counter("stats.errors"),
    )


def _lire_telechargements() -> tuple[int | None, str | None, object]:
    try:
        releases = fetch_releases()
        downloads = sum(release.downloads for release in releases)
        latest_tag = (
            max(releases, key=lambda r: r.version).tag if releases else None
        )
    except Exception as exc:
        return None, None, exc
    return downloads, latest_tag, None


def command_stats(config: Config) -> int:
    state = StateStore(config.watcher.state_file)
    starts, detections, signed, errors = _lire_compteurs(state)
    downloads, latest_tag, erreur = _lire_telechargements()
    _afficher_stats(
        starts, detections, signed, errors, downloads, latest_tag, erreur
    )
    return 0


def _afficher_check_update(channel, policy, erreur=None) -> None:
    if erreur is not None:
        _afficher_update_verification_impossible(erreur)
        return
    if policy is None or not policy.available:
        _afficher_update_a_jour(channel)
        return
    if policy.migration is not None:
        _afficher_migration(policy.migration)
    _afficher_update_disponible(policy.latest.tag, channel)
    _afficher_update_url(policy.latest.url)


def _afficher_migration(release) -> None:
    print(
        f"Migration a passer d'abord : {release.tag} "
        f"({release.migration_reason})"
    )


def _load_release_policy(config: Config) -> tuple[object, object]:
    try:
        policy = update_policy(__version__, channel=config.updates.channel)
    except Exception as exc:
        return None, exc
    return policy, None


def _release_status(config: Config) -> tuple[object, object]:
    return _load_release_policy(config)


def command_check_update(config: Config) -> int:
    policy, erreur = _release_status(config)
    _afficher_check_update(config.updates.channel, policy, erreur)
    return 1 if erreur is not None else 0


def _afficher_update_verification_impossible(erreur: object) -> None:
    print(f"verification impossible : {erreur}")


def _afficher_update_a_jour(channel: str) -> None:
    print(f"CheckMate {__version__} est a jour (canal {channel})")


def _afficher_update_disponible(tag: str, channel: str) -> None:
    print(f"Mise a jour disponible : {tag} (canal {channel})")


def _afficher_update_url(url: str) -> None:
    print(url)


def _afficher_update_annule() -> None:
    print("Annule")


def _afficher_update_telechargement() -> None:
    print("Telechargement et verification de la somme...")


def _afficher_update_echec(erreur: object) -> None:
    print(f"mise a jour impossible : {erreur}")


def _afficher_update_installation(version: object) -> None:
    print(f"Installation de {version} en cours. CheckMate redemarre.")


def _afficher_demander_confirmation(reponse: list[str]) -> None:
    try:
        reponse.append(input("Installer maintenant ? [o/N] ").strip().lower())
    except EOFError:
        reponse.append("")


def _release_pour_update(config: Config):
    policy, erreur = _load_release_policy(config)
    if erreur is not None:
        return None, erreur
    return policy.install_target, None


def _release_ou_code(config: Config):
    release, erreur = _release_pour_update(config)
    if erreur is not None:
        _afficher_update_verification_impossible(erreur)
        return None, 1
    if release is None:
        _afficher_update_a_jour(config.updates.channel)
        return None, 0
    return release, None


def _update_disponible(release, channel: str, check_only: bool) -> int | None:
    _afficher_update_disponible(release.tag, channel)
    if check_only:
        _afficher_update_url(release.url)
        return 0
    return None


def _confirmer_installation(assume_yes: bool) -> bool:
    if assume_yes:
        return True
    reponse: list[str] = []
    _afficher_demander_confirmation(reponse)
    answer = reponse[0] if reponse else ""
    return answer in {"o", "oui", "y", "yes"}


def _installer_update(config: Config) -> int:
    _afficher_update_telechargement()
    try:
        version = update_now(config)
    except UpdateError as exc:
        _afficher_update_echec(exc)
        return 1
    _afficher_update_installation(version)
    return 0


def _installer_si_confirme(config: Config, assume_yes: bool) -> int:
    if not _confirmer_installation(assume_yes):
        _afficher_update_annule()
        return 1
    return _installer_update(config)


def command_update(
    config: Config, *, check_only: bool, assume_yes: bool
) -> int:
    release, code = _release_ou_code(config)
    if code is not None:
        return code
    code = _update_disponible(release, config.updates.channel, check_only)
    if code is not None:
        return code
    return _installer_si_confirme(config, assume_yes)


def _afficher_autostart_install_echec() -> None:
    print("installation du demarrage automatique impossible")


def _afficher_autostart_installe(
    executable: object, config_path: Path
) -> None:
    print(
        f"demarrage automatique installe : {executable} "
        f"--config {config_path} run"
    )


def _afficher_autostart_uninstall_echec() -> None:
    print("desinstallation du demarrage automatique impossible")


def _afficher_autostart_desactive() -> None:
    print("demarrage automatique desactive")


def command_install_autostart(config_path: Path) -> int:
    executable = current_executable()
    config_path = config_path.expanduser().resolve()
    if not enable_autostart(executable, config_path):
        _afficher_autostart_install_echec()
        return 1
    _afficher_autostart_installe(executable, config_path)
    return 0


def command_uninstall_autostart() -> int:
    if not disable_autostart():
        _afficher_autostart_uninstall_echec()
        return 1
    _afficher_autostart_desactive()
    return 0


def _ensure_console_streams() -> None:
    """En mode fenetre (PyInstaller windowed), stdout et stderr valent None."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _afficher_reset_etat_reinitialise(path: Path) -> None:
    print(f"Etat reinitialise : {path}")


def _afficher_reset_aucun_etat(path: Path) -> None:
    print(f"Aucun etat a supprimer : {path}")


def _afficher_main_config_invalide(exc: object) -> None:
    logger.error("configuration invalide : %s", exc)


def _afficher_main_arret_demande() -> None:
    logger.info("arret demande")


def _command_sans_config(args) -> int | None:
    if args.command == "setup":
        return run_setup(
            Path(args.config).expanduser(),
            open_browser=not args.no_browser,
        )
    if args.command == "install-autostart":
        return command_install_autostart(Path(args.config))
    if args.command == "uninstall-autostart":
        return command_uninstall_autostart()
    return None


def _charger_config(args) -> Config | int:
    needs_password = args.command in {"run", "capture", "test-notification"}
    try:
        return load_config(Path(args.config), require_password=needs_password)
    except ConfigError as exc:
        _afficher_main_config_invalide(exc)
        return 2


def _dispatch_update(config: Config, args) -> int | None:
    if args.command != "update":
        return None
    return command_update(config, check_only=args.check, assume_yes=args.yes)


def _dispatch_actions(config: Config, args) -> int | None:
    if args.command == "set-password":
        return command_set_password(config)
    if args.command == "self-test":
        return command_self_test(config, notify=args.notify)
    if args.command == "import-signature":
        return command_import_signature(config, args.file)
    return _dispatch_update(config, args)


def _dispatch_inspection(config: Config, args) -> int | None:
    if args.command == "check-config":
        return command_check_config(config)
    if args.command == "test-notification":
        return command_test_notification(config)
    if args.command == "check-update":
        return command_check_update(config)
    if args.command == "stats":
        return command_stats(config)
    return None


def _dispatch_support(config: Config, args) -> int | None:
    if args.command == "support-bundle":
        return command_support_bundle(
            config, Path(args.config).expanduser(), args.output
        )
    return None


def _dispatch_config(config: Config, args) -> int | None:
    for dispatch in (
        _dispatch_inspection,
        _dispatch_actions,
        _dispatch_support,
    ):
        result = dispatch(config, args)
        if result is not None:
            return result
    return None


def _reset_state(config: Config) -> int:
    path = config.watcher.state_file
    if path.is_file():
        path.unlink()
        _afficher_reset_etat_reinitialise(path)
    else:
        _afficher_reset_aucun_etat(path)
    return 0


def _lancer_surveillance(config: Config, args) -> int:
    options = {
        "once": args.once,
        "dry_run": args.dry_run,
        "auto_override": True if args.auto else None,
        "config_path": Path(args.config).expanduser(),
    }
    return asyncio.run(run_loop(config, **options))


def _run_loop(config: Config, args) -> int:
    try:
        return _lancer_surveillance(config, args)
    except KeyboardInterrupt:
        _afficher_main_arret_demande()
        return 130


def _command_final(config: Config, args) -> int:
    if args.command == "status":
        return command_status(config, Path(args.config).expanduser())
    if args.command == "reset-state":
        return _reset_state(config)
    if args.command == "capture":
        return asyncio.run(command_capture(config))
    return _run_loop(config, args)


def _main_dispatch(args) -> int:
    early = _command_sans_config(args)
    if early is not None:
        return early
    loaded = _charger_config(args)
    if isinstance(loaded, int):
        return loaded
    result = _dispatch_config(loaded, args)
    if result is not None:
        return result
    return _command_final(loaded, args)


def main(argv: list[str] | None = None) -> int:
    _ensure_console_streams()
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    return _main_dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
