# Guide utilisateur

## Ce que fait CheckMate

CheckMate surveille CESAR Emineo pendant tes créneaux de cours. Dès qu'un
formateur ouvre l'émargement, tu reçois une notification, tu confirmes ta
présence, et la signature est rejouée automatiquement.

Pendant l'attente, aucun navigateur visible. Une fenêtre s'ouvre uniquement au
moment de signer, puis se referme.

> **Avertissement.** CheckMate signe uniquement **ta** présence, pour un cours
> auquel tu assistes réellement. Ne l'utilise pas pour falsifier une présence :
> signer pour un cours auquel tu n'assistes pas, ou à la place de quelqu'un
> d'autre, est un usage détourné. L'auteur n'est pas responsable de ce qui est
> fait avec le logiciel. Le projet n'est ni affilié à CESAR, ni à Emineo
> Education, ni à ton établissement ; CESAR et Emineo sont des marques
> d'Emineo Education et de leurs titulaires respectifs. Détails dans les
> [mentions légales](mentions-legales.md).

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
4. À la fin, l'onboarding s'ouvre dans une fenêtre CheckMate native. Si le
   binaire natif manque, il s'ouvre dans ton navigateur.

L'installeur crée un raccourci "CheckMate" dans le menu Démarrer. Le raccourci
ouvre le tableau de bord. L'assistant installe le démarrage automatique à
l'ouverture de session : une entrée `CheckMate` dans la clé `Run` de
l'utilisateur. Le désactiver retire cette entrée, sans toucher au reste de la
configuration.

## Installation sur Linux

Télécharge l'archive `CheckMate-linux-<version>.tar.gz`, extrais-la, puis :

```bash
./install.sh
```

`uv` est requis : https://docs.astral.sh/uv/getting-started/installation/

L'installateur installe l'application dans `~/.local/share/checkmate-watcher`,
crée le service utilisateur systemd, ajoute une entrée **CheckMate** dans le menu
des applications et lance l'onboarding si aucune configuration n'existe.

L'entrée du menu ouvre le tableau de bord dans une fenêtre native CheckMate. Si
le binaire natif manque, le tableau de bord s'ouvre dans le navigateur.
L'assistant installe un service utilisateur systemd
(`checkmate-watcher.service`) ; le désactiver le retire proprement.

## Onboarding

1. **Mise en route** : ce que fait CheckMate et ce qui reste sur l'ordinateur.
2. **Connexion CESAR** : identifiant et mot de passe, avec un test de connexion
   réel dans un navigateur invisible.
3. **Signature** : dessin à la souris ou au doigt. Tu peux aussi importer une
   signature déjà existante au format JSON (liste de points x/y) via le bouton
   "Importer le JSON".
4. **Planning** : jours et créneaux surveillés. Par défaut, du lundi au vendredi,
   09:00-12:00 et 13:30-16:30.
5. **Finition** : test de notification, démarrage automatique, récapitulatif.

![Onboarding, première étape](assets/onboarding.png)

![Fin de configuration](assets/onboarding-finition.png)

## Pendant un cours

- CheckMate vérifie CESAR toutes les 10 secondes, uniquement dans les créneaux.
  La detection se fait en HTTP leger, sans garder Chromium ouvert.
- Dès que l'émargement apparaît, une notification s'affiche.
- Une fenêtre demande "Je suis présent" ou "Absent".
- Sur "Absent", CheckMate arrête la surveillance jusqu'au créneau suivant.
  Ce choix est mémorisé, même après un redémarrage.
- Sur "Je suis présent", un navigateur visible s'ouvre avec la même session CESAR.
  Un overlay CheckMate animé accompagne le tracé, avec un trou autour du canvas,
  puis disparaît avant la validation. La confirmation s'affiche deux secondes,
  puis la fenêtre se referme.
- Le tracé est envoyé en une seule passe, instantanée. Si tu reprends la main et
  signes toi-même, tu peux fermer la fenêtre : CheckMate vérifie l'émargement et
  enregistre la présence au lieu de signaler une erreur.
- Si la detection HTTP échoue ou rencontre un blocage, CheckMate prévient et
  repasse automatiquement sur le navigateur pour le reste du créneau.
- Une fois signé sur un créneau, CheckMate ne vérifie plus rien jusqu'au créneau
  suivant.

Si tu ne réponds pas dans les 3 minutes, rien n'est signé. La demande revient
5 minutes plus tard.

## Tableau de bord et icône

Le raccourci "CheckMate" ouvre le tableau de bord : état de la surveillance,
créneau en cours, prochaine ouverture, compteurs, dernière signature. Il permet
de reconfigurer, tester la notification, vérifier les mises à jour, ouvrir les
logs ou quitter.

Une icône apparaît dans la zone de notification Linux et Windows. Elle change
de couleur selon l'état : active, hors créneau, créneau signé, attente ou
erreur. Son menu propose d'ouvrir le tableau de bord, de reconfigurer, de tester
la notification, de vérifier les mises à jour et de quitter. Sous Windows, un
double-clic sur l'icône ouvre le tableau de bord.

Les notifications sont affichées par le composant natif. Une notification
identique remplace la précédente au lieu de s'empiler. Si le service de
notification du bureau est absent, CheckMate affiche une fenêtre de confirmation
et l'indique dans `checkmate-native.log`, sans bloquer la surveillance.

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

Le transport de detection se configure dans `[watcher]` :

```toml
[watcher]
transport = "http"
http_cookies_file = "~/.local/share/checkmate-watcher/http-cookies.json"
```

`http` est le mode par défaut. `browser` force l'ancien fonctionnement avec
Chromium ouvert pendant la surveillance. Le fichier de cookies HTTP contient la
session CESAR : ne le partage pas et ne le supprime pas pendant un créneau.

Les sélecteurs CESAR peuvent aussi être corrigés à distance depuis un fichier
JSON HTTPS du dépôt. CheckMate le valide, le met en cache et l'utilise en priorité
par rapport aux sélecteurs locaux. En cas de panne réseau, le cache local puis
les valeurs locales sont utilisés. Pour désactiver ce mécanisme :

```bash
export CHECKMATE_REMOTE_SELECTORS=0
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

## Messages de l'équipe

Le mainteneur peut diffuser un court message à toutes les installations :
annonce, panne CESAR, clin d'œil. CheckMate regarde ce canal au démarrage puis
toutes les 5 minutes, et notifie seulement les messages qu'il n'a pas encore
montrés. Un message déjà affiché ne revient pas après un redémarrage.

Le canal est public et ne transmet aucune donnée personnelle : l'application ne
fait que lire la liste des messages. Pour le couper :

```toml
[broadcast]
enabled = false
```

ou avec la variable d'environnement `CHECKMATE_BROADCAST=0`.

## Mises à jour

CheckMate vérifie les nouvelles versions au démarrage et affiche une
notification avec le lien de téléchargement, une seule fois par version. Si la
release stable possède un micro-résumé, la notification explique aussi pourquoi
la mettre à jour. Le même résumé apparaît dans la CLI et le tableau de bord.

### Vérifier et installer

Depuis le tableau de bord, clique sur "Vérifier les mises à jour", puis sur
"Installer X.Y.Z". En terminal :

```bash
checkmate-watcher check-update
checkmate-watcher update --yes
```

CheckMate télécharge le paquet, vérifie sa somme SHA256 et l'installe en
arrière-plan. La configuration et la signature sont conservées.

### Nouveautés après une mise à jour importante

Après une release stable majeure ou mineure, ou lors du passage d'une beta à sa
version stable, CheckMate ouvre le tableau de bord et affiche une fenêtre animée
avec les nouveautés. Le résumé explique les changements en langage simple et
présente les gains mesurés avec leur contexte. Les betas n'ouvrent pas cette
fenêtre.

Le résumé est livré avec l'application, pas téléchargé depuis GitHub. Les simples
correctifs n'ouvrent pas cette fenêtre. Une fois fermée, elle ne réapparaît pas au
redémarrage suivant. Le bouton "Voir les notes complètes" ouvre la release GitHub.

Les comparaisons de latence et de mémoire utilisent des valeurs qui évoluent et
des barres qui se réduisent pour rendre le gain immédiatement lisible.

La fenêtre se ferme avec "C'est parti", la croix ou la touche Échap. Elle est
utilisable au clavier et respecte le réglage système de réduction des animations.

### Choisir le canal stable ou beta

Par défaut, le canal suit la version installée : une version stable utilise le
canal stable, une version beta utilise le canal beta. Une valeur explicite dans
la configuration reste prioritaire. Le tableau de bord affiche le canal à côté
de la version.

Pour recevoir les betas, coche "Recevoir les mises à jour beta" ou configure :

```toml
[updates]
channel = "beta"
```

Pour revenir aux versions stables, décoche la case ou remets
`channel = "stable"`. Si tu es déjà sur une beta, tu restes sur cette version :
les prochaines betas ne sont plus proposées, mais CheckMate ne retourne jamais
automatiquement à une version stable plus ancienne. La prochaine version stable
plus récente te sera proposée.

L'ancienne clé `include_prerelease = true` reste acceptée et équivaut à
`channel = "beta"` si `channel` est absent.

### Mise à jour obligatoire

Si une release impose une version minimale, CheckMate ne démarre pas la
surveillance et ne signe rien. Le tableau de bord affiche un bandeau rouge
avec la raison et un bouton pour installer la version exigée. L'icône passe en
« attention requise ». En terminal, `checkmate-watcher run --once` sort avec le
code 3.

Le tableau de bord reste disponible pour installer la mise à jour, consulter
les logs ou quitter. Si GitHub est injoignable, le contrôle échoue ouvert :
CheckMate ne se bloque pas à cause d'une panne réseau.

### Migration intermédiaire

Certaines versions doivent être installées dans l'ordre pour migrer un format
de données. Dans ce cas, le tableau de bord affiche un bandeau orange
"Migration intermédiaire requise" avec la raison et la version à installer en
premier.

Clique sur "Installer X.Y.Z" pour appliquer cette migration. Après le
redémarrage, CheckMate indique l'étape suivante si nécessaire. Plusieurs
migrations peuvent donc s'enchaîner une par une. Le retour arrière sous une
version qui a migré les données n'est pas garanti.

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

## Statistiques anonymes

CheckMate compte les installations et les signatures avec un identifiant
aléatoire, sans aucune donnée CESAR. Pour couper ces envois :

```toml
[analytics]
enabled = false
```

ou lance l'application avec `CHECKMATE_ANALYTICS=0`. Voir la
[page vie privée](vie-privee.md).

## Limites

- La machine doit être allumée et la session ouverte. En veille, la reprise est
  détectée en quelques minutes.
- Si CESAR ajoute une validation supplémentaire (2FA, captcha), la connexion
  automatique échouera et le self-test le signalera.
- Une mise à jour de CESAR peut casser les sélecteurs. Les logs indiquent alors
  qu'aucun bouton n'est trouvé.
- CheckMate signe à ta place, avec ta signature, uniquement si tu es présent.
  Ne l'utilise pas pour falsifier une présence : l'auteur n'est pas responsable
  de ce qui est fait avec le logiciel.
