# Guide utilisateur

## Ce que fait CheckMate

CheckMate surveille CESAR Emineo pendant tes créneaux de cours. Dès qu'un
formateur ouvre l'émargement, tu reçois une notification, tu confirmes ta
présence, et la signature est rejouée automatiquement.

Pendant l'attente, aucun navigateur visible. Une fenêtre s'ouvre uniquement au
moment de signer, puis se referme.

## Prérequis

- Windows 10 ou 11, ou une distribution Linux avec systemd.
- Microsoft Edge, Google Chrome, Chromium, ou le Chromium de Playwright.
- L'ordinateur allumé et la session ouverte au moment du cours.

## Installation sur Windows

1. Télécharge `CheckMate-Setup-<version>.exe` depuis les releases GitHub.
2. Lance l'installeur. Il s'installe dans ton dossier utilisateur, sans droits
   administrateur.
3. Windows SmartScreen peut afficher un avertissement tant que l'exécutable
   n'est pas signé. Clique sur "Informations complémentaires" puis
   "Exécuter quand même".
4. À la fin, l'onboarding s'ouvre dans une fenêtre CheckMate native. Si
   WebView2 est absent, il s'ouvre dans ton navigateur.

L'installeur crée un raccourci "CheckMate" dans le menu Démarrer. Le raccourci
ouvre le tableau de bord. L'assistant installe le démarrage automatique à
l'ouverture de session.

## Installation sur Linux

Télécharge l'archive `CheckMate-linux-<version>.tar.gz`, extrais-la, puis :

```bash
./install.sh
```

`uv` est requis : https://docs.astral.sh/uv/getting-started/installation/

L'installateur installe l'application dans `~/.local/share/checkmate-watcher`,
crée le service utilisateur systemd, ajoute une entrée **CheckMate** dans le menu
des applications et lance l'onboarding si aucune configuration n'existe.

L'entrée du menu ouvre le tableau de bord dans une fenêtre native, si PyGObject,
GTK 3 et WebKit2 sont installés. Sinon, il s'ouvre dans le navigateur.

## Onboarding

1. **Mise en route** : ce que fait CheckMate et ce qui reste sur l'ordinateur.
2. **Connexion CESAR** : identifiant et mot de passe, avec un test de connexion
   réel dans un navigateur invisible.
3. **Signature** : dessin à la souris ou au doigt. Si tu utilisais l'extension,
   clique sur "Exporter" dans sa section Signature, puis "Importer le JSON"
   dans l'assistant.
4. **Planning** : jours et créneaux surveillés. Par défaut, du lundi au vendredi,
   09:00-12:00 et 13:30-16:30.
5. **Finition** : test de notification, démarrage automatique, récapitulatif.

![Onboarding, première étape](assets/onboarding.png)

![Fin de configuration](assets/onboarding-finition.png)

## Pendant un cours

- CheckMate vérifie CESAR toutes les 10 secondes, uniquement dans les créneaux.
- Dès que le bouton d'émargement apparaît, une notification s'affiche.
- Une fenêtre demande "Je suis présent" ou "Absent".
- Sur "Je suis présent", un navigateur visible s'ouvre, signe, affiche la
  confirmation deux secondes, puis se referme.
- Une fois signé sur un créneau, CheckMate ne vérifie plus rien jusqu'au créneau
  suivant.

Si tu ne réponds pas dans les 3 minutes, rien n'est signé. La demande revient
5 minutes plus tard.

## Tableau de bord et icône

Le raccourci "CheckMate" ouvre le tableau de bord : état de la surveillance,
créneau en cours, prochaine ouverture, compteurs, dernière signature. Il permet
de reconfigurer, tester la notification, vérifier les mises à jour, ouvrir les
logs ou quitter.

Une icône apparaît dans la zone de notification Windows. Elle change de couleur
selon l'état : active, hors créneau, créneau signé ou erreur.

## Modifier la configuration

Depuis le tableau de bord, clique sur "Reconfigurer". L'assistant s'ouvre dans
un nouvel onglet. Après l'avoir terminé, quitte CheckMate puis relance-le depuis
le menu Démarrer pour appliquer les changements.

En terminal, sur Linux :

```bash
checkmate-watcher setup
```

Pour changer le mot de passe seul :

```bash
checkmate-watcher set-password
```

Pour créer une archive de diagnostic sans secret :

```bash
checkmate-watcher support-bundle
```

Pour oublier les émargements déjà traités, par exemple après un test :

```bash
checkmate-watcher reset-state
```

Puis redémarre le service :

```bash
systemctl --user restart checkmate-watcher
```

## Mises à jour

CheckMate vérifie les nouvelles versions au démarrage et affiche une
notification avec le lien de téléchargement, une seule fois par version.

Pour vérifier manuellement :

```bash
checkmate-watcher check-update
```

L'installation est encore manuelle : télécharge le nouvel installeur depuis les
releases. L'OTA complet sera activé après la mise en place de la signature de
code.

## Vérifier l'installation

```bash
checkmate-watcher self-test --notify
```

Le diagnostic vérifie le mot de passe, la signature, le navigateur, le
trousseau, le démarrage automatique, le planning et le dossier de données.
Sur Windows, relance le raccourci "CheckMate" et utilise "Tester la
notification" dans l'assistant.

Le chemin des logs s'affiche avec :

```bash
checkmate-watcher --config ~/.config/checkmate-watcher/config.toml check-config
```

Sur Linux : `journalctl --user -u checkmate-watcher -f`.
Sur Windows : `%LOCALAPPDATA%\checkmate-watcher\Logs\checkmate-watcher.log`.

## Désinstallation

**Windows** : Paramètres, Applications, CheckMate, Désinstaller. Le démarrage
automatique est supprimé. La configuration et la signature restent dans
`%LOCALAPPDATA%\checkmate-watcher` si tu veux les supprimer à la main.

**Linux** :

```bash
systemctl --user disable --now checkmate-watcher
rm ~/.config/systemd/user/checkmate-watcher.service
rm -rf ~/.local/share/checkmate-watcher
rm -rf ~/.config/checkmate-watcher
```

## Mettre à jour

Le tableau de bord propose la mise à jour : "Vérifier les mises à jour", puis
"Installer X.Y.Z". CheckMate télécharge le paquet, vérifie sa somme SHA256 et
l'installe en arrière-plan. La configuration et la signature sont conservées.

En terminal :

```bash
checkmate-watcher update --check
checkmate-watcher update --yes
```

### Choisir le canal stable ou beta

Par défaut, ton installation suit les versions stables : une beta ne t'est
jamais proposée. Le tableau de bord affiche le canal à côté de la version.

Pour recevoir les betas, ajoute `channel = "beta"` dans la section `[updates]`
de ta configuration :

```toml
[updates]
channel = "beta"
```

Le bouton "Installer X.Y.Z" installe la version proposée pour ton canal, sans
autre choix à faire. Pour revenir aux versions stables, remets
`channel = "stable"` ou supprime la clé (c'est la valeur par défaut).

L'ancienne clé `include_prerelease = true` reste acceptée et équivaut à
`channel = "beta"` si `channel` est absent.

## Limites

- La machine doit être allumée et la session ouverte. En veille, la reprise est
  détectée en quelques minutes.
- Si CESAR ajoute une validation supplémentaire (2FA, captcha), la connexion
  automatique échouera et le self-test le signalera.
- Une mise à jour de CESAR peut casser les sélecteurs. Les logs indiquent alors
  qu'aucun bouton n'est trouvé.
- CheckMate signe à ta place, avec ta signature. Tu restes responsable de son
  usage.
