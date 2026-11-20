# Dépannage

## Premier réflexe

```bash
checkmate-watcher self-test --notify
```

Le diagnostic indique ce qui manque : mot de passe, signature, navigateur,
trousseau, démarrage automatique, planning, dossier de données. Ajoute
`--verbose` pour les détails.

## Logs

```bash
# Linux
journalctl --user -u checkmate-watcher -f

# chemin du fichier de logs
checkmate-watcher check-config
```

Sur Windows, ouvre `%LOCALAPPDATA%\checkmate-watcher\Logs\checkmate-watcher.log`.
Les lignes utiles contiennent `bouton d'emargement detecte`, `connexion
reussie`, `signature` ou `ERREUR`.

## Aucune notification

1. Lance `checkmate-watcher test-notification`.
2. Coupe le mode silencieux, "Ne pas déranger" ou "Concentration".
3. Sur Windows, autorise CheckMate dans les notifications système.
4. Dans l'assistant, la case "J'ai vérifié que la notification s'affiche"
   doit être cochée pour terminer la configuration.
4. Sur Linux, `notify-send` peut être cassé : CheckMate bascule alors sur D-Bus.
   Le self-test le signale.

## L'émargement n'est pas détecté

1. Vérifie l'heure : hors créneau, CheckMate ne fait rien. `check-config` affiche
   les plages.
2. Vérifie que le créneau du jour n'est pas déjà marqué signé :
   ```bash
   checkmate-watcher reset-state
   systemctl --user restart checkmate-watcher
   ```
3. Lance un contrôle manuel :
   ```bash
   checkmate-watcher run --once --dry-run -v
   ```
4. Si la connexion échoue, vérifie le mot de passe avec `set-password`.
5. Si CESAR a changé son interface, les logs affichent `aucun bouton
   d'emargement visible`. Les sélecteurs sont configurables dans
   `[selectors]`, mais il faut généralement mettre à jour CheckMate.

## Le service ne tourne pas

**Linux** :

```bash
systemctl --user status checkmate-watcher
systemctl --user restart checkmate-watcher
```

**Windows** :

```powershell
schtasks /Query /TN CheckMate
schtasks /Run /TN CheckMate
```

Si la tâche existe mais échoue, regarde les logs. Un redémarrage de session
suffit souvent après une mise à jour.

## Le navigateur est introuvable

Installe Microsoft Edge ou Google Chrome, ou :

```bash
uv run playwright install chromium
```

Tu peux aussi forcer un chemin dans la configuration :

```toml
[watcher]
executable_path = "/usr/bin/chromium"
```

## La signature est refusée

Relance `checkmate-watcher setup`, refais le tracé, puis vérifie la confirmation
affichée par CESAR. Si le site répond autre chose que "présence prise en
compte", la signature n'a pas été validée.

## La fenêtre visible ne s'ouvre pas

- vérifie que la session graphique est active ;
- sur Linux, teste `DISPLAY` et `WAYLAND_DISPLAY` ;
- sur Windows, vérifie qu'Edge ou Chrome démarre normalement.

## Support

Crée une archive propre avec :

```bash
checkmate-watcher support-bundle
```

Envoie :

- la sortie de `self-test --notify` ;
- les 50 dernières lignes de logs ;
- la configuration **sans le mot de passe** (`check-config` masque déjà le
  secret).

Ne partage jamais `~/.config/checkmate-watcher/env`, `%LOCALAPPDATA%\checkmate-watcher\config.toml`
s'il contient `password`, ni le dossier du profil Chromium.
