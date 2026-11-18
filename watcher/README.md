# CheckMate watcher

Script Python qui surveille CESAR Emineo en continu, rafraichit le tableau de bord,
et propose de signer l'emargement des que le bouton apparait. Plus besoin de garder
un onglet ouvert ni de cliquer sur "pointer" : une notification desktop s'affiche,
tu choisis "Je suis present" et la signature est rejouee automatiquement.

## Pourquoi un rafraichissement

Le bouton d'emargement n'apparait pas tout seul : le site doit etre recharge. Le
script recharge donc la page a chaque cycle (`poll_interval`, 60 s par defaut).
La detection arrive au pire un intervalle apres l'ouverture par le formateur.

## Installation

```bash
cd watcher
uv sync
uv run playwright install chromium   # ou renseigne executable_path plus bas
mkdir -p ~/.config/checkmate-watcher ~/.local/share/checkmate-watcher
cp config.example.toml ~/.config/checkmate-watcher/config.toml
chmod 600 ~/.config/checkmate-watcher/config.toml
```

Si tu ne veux pas telecharger le Chromium de Playwright, utilise celui du systeme :

```toml
[watcher]
executable_path = "/usr/bin/chromium"
```

Renseigne `username` et le mot de passe. Le plus propre est de le garder hors du
fichier :

```bash
# ~/.config/environment.d/checkmate.conf ou export dans le shell
export CHECKMATE_PASSWORD="..."
```

## Signature

Deux possibilites :

1. Creer une signature avec le script :
   ```bash
   uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml capture
   ```
2. Reutiliser celle de l'extension : copie le contenu de `signatureData` depuis
   `chrome.storage.local` dans `~/.config/checkmate-watcher/signature.json`.
   Les deux formats sont acceptes (`[{x,y,type}]` ou `{"signatureData": [...]}`).

## Utilisation

```bash
# verification de la configuration
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml check-config

# test des notifications et de la fenetre de confirmation
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml test-notification

# un seul cycle, sans rien signer
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml run --once --dry-run -v

# surveillance continue
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml run

# signature automatique sans confirmation
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml run --auto
```

La premiere execution ouvre un navigateur visible : connecte-toi une fois
manuellement si besoin, le profil persistant garde la session.

## Service utilisateur

```bash
mkdir -p ~/.config/systemd/user
cp systemd/checkmate-watcher.service ~/.config/systemd/user/
# adapter le chemin de l'executable si besoin
ln -sf "$(pwd)/.venv/bin/checkmate-watcher" ~/.local/bin/checkmate-watcher
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR
systemctl --user daemon-reload
systemctl --user enable --now checkmate-watcher
journalctl --user -u checkmate-watcher -f
```

## Comportement

- Chaque cycle : `goto` du tableau de bord, attente du rendu JS, recherche de
  `button.buttonPresent`.
- Si le bouton est la et que l'emargement n'a pas deja ete traite : notification
  `notify-send` + fenetre `zenity` avec "Je suis present" / "Absent".
- Sur "Present" : clic, tracé de la signature au clavier/souris Playwright,
  validation, lecture de la confirmation.
- Deduplication par identifiant d'emargement et date, TTL configurable.
- Trois erreurs consecutives declenchent un redemarrage du navigateur.

## Limites

- Chrome/Chromium doit tourner, donc la session graphique doit etre ouverte.
- Les selecteurs CSS peuvent casser si CESAR change son interface : ils sont
  configurables dans `[selectors]`.
- Le mot de passe est lu depuis l'environnement par defaut ; evite le stockage en
  clair dans le TOML.
- Si le site demande une validation supplementaire (2FA, captcha), la connexion
  automatique echouera et le script le signalera dans les logs.

## Tests

```bash
uv run pytest
```
