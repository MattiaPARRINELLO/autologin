# CheckMate UI (Rust)

Interface native en Rust avec egui, sans navigateur ni WebView. Elle lit l'API
locale du moteur Python (`/api/status`, `/api/action`) via `runtime.json`.

## Lancer

Le moteur Python doit tourner :

```bash
cd ../watcher
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml run
```

Puis, dans `ui/` :

```bash
cargo run
```

Si le moteur n'est pas lancé, la fenêtre propose de le démarrer. Le chemin du
moteur peut être forcé avec `CHECKMATE_BACKEND=/chemin/vers/checkmate-watcher`.

## Etat

- tableau de bord natif : état, créneaux, compteurs, dernières dates
- actions : tester la notification, vérifier les mises à jour, ouvrir les logs,
  quitter
- démarrage du moteur depuis la fenêtre
- l'onboarding et la signature ne sont pas encore portés en Rust

## Architecture

Le Rust ne dépend pas du HTML. Il parle à l'API locale du moteur Python :

- `GET /api/status`
- `POST /api/action`

Le jeton et le port sont lus dans `runtime.json` (dossier de données
CheckMate). L'icône de notification reste portée par le moteur Python pour
l'instant.
