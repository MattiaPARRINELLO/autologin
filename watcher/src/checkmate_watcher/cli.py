"""Point d'entree en ligne de commande."""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from . import __version__, notify
from .browser import missing_browser_message, resolve_executable
from .config import Config, ConfigError, load_config
from .signature import SignatureError, load_signature, parse_points, save_signature
from .watcher import run_loop

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "~/.config/checkmate-watcher/config.toml"

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

  document.getElementById('clear').addEventListener('click', () => {
    state.points.length = 0;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  document.getElementById('save').addEventListener('click', () => {
    if (state.points.length < 2) return;
    state.done = true;
  });
</script>
</body>
</html>
"""


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


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
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _mask(value: str) -> str:
    if not value:
        return "(vide)"
    return "*" * min(len(value), 8) + f" ({len(value)} caracteres)"


def command_check_config(config: Config) -> int:
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
    print(f"  Profil         : {config.watcher.profile_dir}")
    print(f"  Etat           : {config.watcher.state_file}")
    print(f"  Signature      : {config.signature.file}")

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
        executable = resolve_executable(playwright.chromium, config)
        options = {"executable_path": executable} if executable else {}
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
        except Exception as exc:  # noqa: BLE001
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
    sent = notify.send(
        "CheckMate",
        "Ceci est une notification de test.",
        app_name=config.notifications.app_name,
        icon=config.notifications.icon,
        urgency="normal",
    )
    print("notification envoyee" if sent else "notification impossible")
    answer = notify.ask(
        "Ceci est une confirmation de test. Clique sur un bouton.",
        timeout=60,
        title=config.notifications.app_name,
    )
    print(f"reponse : {answer}")
    return 0 if sent else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        logger.error("configuration invalide : %s", exc)
        return 2

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
            )
        )
    except KeyboardInterrupt:
        logger.info("arret demande")
        return 130


if __name__ == "__main__":
    sys.exit(main())
