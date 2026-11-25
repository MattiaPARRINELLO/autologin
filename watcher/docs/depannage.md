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
Les lignes utiles contiennent `emargement HTTP detecte`, `bouton d'emargement
detecte`, `transport HTTP indisponible`, `connexion reussie`, `signature` ou
`ERREUR`.

## Aucune notification

1. Lance `checkmate-watcher test-notification`.
2. Coupe le mode silencieux, "Ne pas déranger" ou "Concentration".
3. Sur Windows, autorise CheckMate dans les notifications système : Paramètres >
   Système > Notifications > CheckMate doit être activé.
4. Si tu as installé CheckMate via l'installeur, la notification s'affiche sous
   le nom "CheckMate" ; en mode portable (archive zip), elle s'affiche sous
   "Windows PowerShell", ce qui est normal.
5. Dans l'assistant, la case "J'ai vérifié que la notification s'affiche"
   doit être cochée pour terminer la configuration.
6. Sur Linux, `notify-send` peut être cassé : CheckMate bascule alors sur D-Bus.
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
5. En mode HTTP, un calendrier absent, un challenge ou une erreur 403/429/5xx
   déclenche le repli navigateur. Si les logs affichent `transport HTTP
   indisponible`, vérifie la connexion et la session CESAR.
6. Si CESAR a changé son interface, les logs affichent `aucun bouton
   d'emargement visible` ou `calendrier CESAR absent`. Les sélecteurs navigateur
   restent configurables dans `[selectors]`, mais une mise à jour est souvent
   nécessaire.
7. Pour forcer l'ancien fonctionnement et comparer :

   ```toml
   [watcher]
   transport = "browser"
   ```

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

## La fenêtre CheckMate ne s'ouvre pas

CheckMate affiche son tableau de bord dans une fenêtre native via WebView2. Sous
Windows 10 et 11, WebView2 est déjà présent avec Edge. S'il manque, CheckMate
essaie le navigateur par défaut.

Si rien ne s'ouvre, installe le Runtime WebView2 depuis Microsoft, ou force le
navigateur :

```powershell
$env:CHECKMATE_BROWSER = "1"
CheckMate.exe status
```

Sous Linux, la fenêtre native demande GTK et WebKitGTK. Installe `python-gobject`
et `webkit2gtk-4.1` sur Arch et Garuda, ou `python3-gi` et `gir1.2-webkit2-4.1`
sur Debian et Ubuntu. Sans eux, CheckMate ouvre la page dans le navigateur.

## La mise à jour échoue

CheckMate refuse d'installer un paquet dont la somme SHA256 ne correspond pas à
celle publiée. Vérifie la connexion réseau, puis réessaie. En cas d'échec
répété, télécharge l'installeur depuis la page des releases et lance-le à la
main.

Si l'application ne redémarre pas après la mise à jour, relance-la depuis le
menu des applications. Les logs se trouvent dans
`~/.local/state/checkmate-watcher/log/checkmate-watcher.log` sous Linux, et dans
`%LOCALAPPDATA%\checkmate-watcher\logs` sous Windows.

## CheckMate demande une mise à jour obligatoire

Un bandeau rouge « Mise à jour obligatoire » signifie qu'une version minimale a
été publiée pour corriger un problème de sécurité ou de compatibilité. La
surveillance reste arrêtée jusqu'à l'installation. Utilise le bouton du tableau
de bord ou lance :

```bash
checkmate-watcher update --yes
```

Le motif du blocage est affiché dans le bandeau. Si GitHub est injoignable,
CheckMate ne se bloque pas : réessaie quand la connexion revient.

## Une migration intermédiaire est demandée

Un bandeau orange « Migration intermédiaire requise » indique une version à
installer avant la cible finale. Installe la version affichée, laisse CheckMate
redémarrer, puis répète l'opération si une autre étape est proposée. Ne saute
pas ces étapes avec une archive plus récente.

Comme une migration peut être irréversible, sauvegarde tes données avant
l'installation :

- Linux : `~/.config/checkmate-watcher` et `~/.local/share/checkmate-watcher` ;
- Windows : `%LOCALAPPDATA%\checkmate-watcher`.

## L'icône de notification est un carré plein

Sous Linux, CheckMate publie une icône StatusNotifierItem avec un vrai pixmap de
64 pixels. Si Plasma ou la barre des tâches affiche encore un aplat, la session
n'expose peut-être pas D-Bus. Vérifie que `DBUS_SESSION_BUS_ADDRESS` est défini,
ou force l'ancien backend XEmbed :

```bash
CHECKMATE_TRAY=xorg checkmate-watcher status
```

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

Si le message parle d'un tracé "réduit à un point", la signature enregistrée ou
rejouée ne contient qu'un clic : redessine-la dans l'assistant (le tracé doit
couvrir la zone) puis relance. CheckMate préfère échouer plutôt que de valider
un émargement avec un point.

## La fenêtre visible ne s'ouvre pas

- vérifie que la session graphique est active ;
- sur Linux, teste `DISPLAY` et `WAYLAND_DISPLAY` ;
- sur Windows, vérifie qu'Edge ou Chrome démarre normalement.

## Support

Crée une archive propre avec :

```bash
checkmate-watcher support-bundle
```

Le bundle contient la sortie de diagnostic, la configuration sans mot de passe
et les dernières lignes de logs.

Depuis la prochaine version, il embarque aussi `diagnostics/`, les cinq
dernières tentatives de signature :

- `diagnostic.json` : taille du canvas et de la page, densité de pixels,
  élément qui recouvre le canvas, nombre d'événements reçus (dont ceux de
  confiance), encre mesurée, longueur de la valeur enregistrée par le site ;
- `canvas.png` : ce qui a été réellement tracé dans le canvas ;
- `page.png` : la page au moment du tracé.

C'est ce qu'il faut pour reproduire un cas où la signature part de travers.

Envoie aussi la sortie de `self-test`.

Ne partage jamais `~/.config/checkmate-watcher/env`, `%LOCALAPPDATA%\checkmate-watcher\config.toml`
s'il contient `password`, `http-cookies.json` ni le dossier du profil Chromium.
