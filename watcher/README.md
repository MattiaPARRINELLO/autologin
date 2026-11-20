# CheckMate watcher

Script Python qui surveille CESAR Emineo en continu, rafraichit le tableau de bord,
et propose de signer l'emargement des que le bouton apparait. Plus besoin de garder
un onglet ouvert ni de cliquer sur "pointer" : une notification desktop s'affiche,
tu choisis "Je suis present" et la signature est rejouee automatiquement.

## Pourquoi un rafraichissement

Le bouton d'emargement n'apparait pas tout seul : le site doit etre recharge. Le
script recharge donc la page a chaque cycle (`poll_interval`, 60 s par defaut).
La detection arrive au pire un intervalle apres l'ouverture par le formateur.

## Plateformes

| Plateforme | Notifications | Confirmation | Navigateur | Demarrage auto |
|------------|---------------|--------------|------------|----------------|
| Linux | notify-send, fallback D-Bus | zenity, fallback tkinter | Chromium systeme ou bundle | systemd utilisateur |
| Windows | toast PowerShell, valide sur runner GitHub | tkinter | Edge ou Chrome installe | registre utilisateur valide |
| macOS | osascript | tkinter | Chrome / Edge installe | launchd prevu |

Les chemins sont portables via `platformdirs` : `~/.config/checkmate-watcher` sur
Linux, `%LOCALAPPDATA%\checkmate-watcher` sur Windows. Les logs tournent dans
`checkmate-watcher.log` avec rotation, en plus de stdout.

## Documentation

- [Guide utilisateur](docs/guide-utilisateur.md)
- [Vie privée](docs/vie-privee.md)
- [Dépannage](docs/depannage.md)
- [Mentions légales](docs/mentions-legales.md)
- [Validation Windows](docs/windows-validation.md)
- [Présentation HTML](presentation/index.html)

## Onboarding

```bash
checkmate-watcher setup
```

Ouvre une page locale en 5 etapes : presentation, identifiants avec test de
connexion reel, signature, planning, test de notification et installation du
demarrage automatique. Aucune donnee ne sort de la machine et la page n'est
accessible que depuis 127.0.0.1 avec un jeton aleatoire.

## Windows

Une pre-version de l'installeur `.exe` est publiee dans les releases, non signee
tant que SignPath n'est pas actif. Pour developper, sur une machine avec Python
et [uv](https://docs.astral.sh/uv/) :

```powershell
cd watcher
uv sync
uv run checkmate-watcher --config "$env:APPDATA\checkmate-watcher\config.toml" set-password
uv run checkmate-watcher --config "$env:APPDATA\checkmate-watcher\config.toml" capture
uv run checkmate-watcher --config "$env:APPDATA\checkmate-watcher\config.toml" install-autostart
uv run checkmate-watcher --config "$env:APPDATA\checkmate-watcher\config.toml" self-test --notify
```

Le mot de passe part dans le Credential Manager, le demarrage auto dans une tache
planifiee au logon, et les notifications utilisent les toasts Windows.
La checklist de validation reelle est dans
[`docs/windows-validation.md`](docs/windows-validation.md), avec
`scripts/windows-check.ps1`.

Commandes utiles partout :

```bash
checkmate-watcher self-test          # diagnostic complet
checkmate-watcher set-password       # stocke le mot de passe dans le trousseau
checkmate-watcher install-autostart  # tache planifiee / service systemd
checkmate-watcher uninstall-autostart
checkmate-watcher support-bundle
checkmate-watcher check-update
```

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

## Demarrage automatique

Apres avoir cree la config reelle (`~/.config/checkmate-watcher/config.toml`) :

```bash
./scripts/install-service.sh
```

Le script copie l'application dans `~/.local/share/checkmate-watcher/app` avec
son propre venv, cree `~/.local/bin/checkmate-watcher`, installe l'unite
systemd, cree `~/.config/checkmate-watcher/env` pour le mot de passe, puis
active et demarre le service. Il redemarre a chaque connexion.

L'installation ne depend plus du dossier de travail : relance simplement
`./scripts/install-service.sh` apres une mise a jour du code. Si le venv de
l'application disparait, le lanceur le reconstruit automatiquement avec `uv`.

```bash
# suivre les logs
journalctl --user -u checkmate-watcher -f
# arreter ou desactiver
systemctl --user stop checkmate-watcher
systemctl --user disable checkmate-watcher
```

Avec le planning active, le service demarre avec la session mais ne lance aucun
navigateur avant le premier creneau de la journee.

## Plages horaires

La surveillance ne tourne que sur les creneaux de cours :

```toml
[schedule]
enabled = true
days = ["mon", "tue", "wed", "thu", "fri"]
windows = ["09:00-12:00", "13:30-16:30"]
```

- hors plage : aucune verification, le navigateur est ferme, reprise a 5 s pres
  au debut du creneau suivant
- une fois la presence signee dans un creneau, plus aucune verification jusqu'au
  creneau suivant (memoire persistante, meme apres un redemarrage)
- un emargement manque ou refuse n'empeche pas de reessayer dans le meme creneau
- `--once` hors plage se contente d'afficher la prochaine ouverture et sort

Pour desactivee completement le planning : `enabled = false`.

## Comportement

- Surveillance invisible : le navigateur reste en mode headless pendant l'attente,
  aucune fenetre ne s'ouvre.
- `visible_on_sign = true` (defaut) : au moment de signer seulement, le navigateur
  se relance en mode visible avec le meme profil, fait la signature, affiche la
  confirmation deux secondes, puis se referme et repasse en invisible.
- Chaque cycle (10 a 15 s) : `goto` du tableau de bord, attente adaptative du
  rendu JS, recherche de `button.buttonPresent`. Detection typique en 10 a 15 s
  apres l'ouverture par le formateur.
- Si le bouton est la et que l'emargement n'a pas deja ete traite : notification
  `notify-send` + fenetre `zenity` avec "Je suis present" / "Absent".
- Sur "Present" : clic, tracé de la signature au clavier/souris Playwright,
  validation, lecture de la confirmation.
- Deduplication par identifiant d'emargement et date, TTL configurable.
- Si personne ne repond a la confirmation, l'emargement n'est pas marque comme
  traite : la demande revient apres `prompt_retry` (300 s par defaut).
- Repondre "Absent" marque l'emargement comme traite pour la duree du TTL.
- Trois erreurs consecutives declenchent un redemarrage du navigateur.
- Si `notify-send` est casse sur la machine, les notifications basculent
  automatiquement sur D-Bus (`gdbus`).

## Limites

- Chrome/Chromium doit tourner, donc la session graphique doit etre ouverte.
- Les selecteurs CSS peuvent casser si CESAR change son interface : ils sont
  configurables dans `[selectors]`.
- Le mot de passe est lu depuis l'environnement par defaut ; evite le stockage en
  clair dans le TOML.
- Si le site demande une validation supplementaire (2FA, captcha), la connexion
  automatique echouera et le script le signalera dans les logs.

## Tester

### 1. Sans rien toucher au vrai CESAR

Un emulateur autonome vit dans [`../emulator/`](../emulator/) :

```bash
python3 emulator/server.py --port 8787
```

Puis, dans un autre terminal :

```bash
uv run checkmate-watcher --config ../emulator/watcher.toml run -v
```

Ouvre `http://127.0.0.1:8787/admin` et clique sur "Ouvrir l'emargement".
Le cycle suivant doit detecter le bouton et proposer la signature. L'etat passe
a "signe" dans l'admin.

Test complet automatise (Chromium requis) :

```bash
CHECKMATE_E2E=1 uv run pytest tests/test_emulator_e2e.py -v
```

### 2. Contre le vrai CESAR, sans risque

```bash
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml run --once --dry-run -v
```

Le mode `--dry-run` se connecte, rafraichit et affiche s'il trouve un bouton,
sans notifier ni signer.

### 3. Verification des briques

```bash
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml check-config
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml test-notification
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml capture
uv run checkmate-watcher --config ~/.config/checkmate-watcher/config.toml reset-state
```

`reset-state` efface la memoire des emargements deja traites, utile apres un test
ou un redemarrage de l'emulateur.

### 4. Tests unitaires

```bash
uv run pytest
```

