# Architecture du watcher

Cette page decrit l'application Python de `watcher/` : ses modules, le flux d'un
cycle de surveillance et les frontieres entre les composants. Elle sert de carte
avant de lire le code.

## Vue d'ensemble

Le watcher est un processus unique qui :

1. charge la configuration TOML et la signature ;
2. decide si la surveillance est autorisee par le planning ;
3. pilote un Chromium headless avec Playwright pour interroger CESAR ;
4. demande confirmation a l'utilisateur quand un emargement apparait ;
5. signe, memorise l'emargement traite et attend le cycle suivant ;
6. expose un tableau de bord local (HTTP sur `127.0.0.1`) et une icone de
   notification tant qu'il tourne.

Aucun service CheckMate n'intervient dans la surveillance : le seul reseau
sortant va vers CESAR, vers l'API GitHub des releases si les mises a jour sont
activees, et vers le compteur de statistiques anonymes si `[analytics]` reste
active.

## Carte des modules

| Module | Role |
|--------|------|
| `cli.py` | point d'entree `checkmate-watcher` : commandes `run`, `setup`, `status`, `capture`, `self-test`, `update`, `support-bundle`, etc. |
| `watcher.py` | boucle de surveillance `run_loop`, orchestration des decisions et des signatures |
| `cesar.py` | `CesarSession` : navigation Playwright, connexion, detection de l'emargement, trace de la signature |
| `browser.py` | choix du navigateur : config, Chromium de Playwright, navigateur systeme |
| `config.py` | chargement et validation du TOML (`[cesar]`, `[watcher]`, `[schedule]`, `[notifications]`, `[updates]`, `[selectors]`) |
| `schedule.py` | plages horaires, creneau courant, prochaine ouverture |
| `signature.py` | lecture, mise a l'echelle et sauvegarde des points de signature |
| `notifications.py` | notifications bureau et fenetre de confirmation, par plateforme |
| `credentials.py` | mot de passe dans le trousseau systeme quand il est disponible |
| `state.py` | etat persistant : emargements traites, creneaux signes, compteurs |
| `local_http.py` | socle HTTP commun : ecoute locale, jeton, en-tetes de securite, lecture JSON |
| `status_server.py` | serveur HTTP local du tableau de bord (`/api/status`, `/api/action`) et fichier `runtime.json` |
| `status_ui.py` | page HTML du tableau de bord |
| `status_data.py` | construction de l'instantane affiche par le tableau de bord |
| `setup_server.py` | serveur HTTP local de l'onboarding (`/api/state`, `/api/test-login`, `/api/signature`, `/api/schedule`, `/api/finish`, etc.) |
| `setup_ui.py` | page HTML de l'onboarding |
| `window.py` | fenetre native pywebview, avec repli navigateur |
| `tray.py`, `sni.py` | icone de notification : `pystray` et StatusNotifierItem Linux |
| `autostart.py` | service systemd utilisateur ou tache planifiee Windows |
| `updates.py` | lecture des releases GitHub, marqueurs de release, canal, version minimale et migration |
| `analytics.py` | compteurs d'usage anonymes : installation et signature |
| `self_update.py` | installation de la cible de mise a jour par un processus detache |
| `support.py` | archive de diagnostic sans mot de passe ni signature |
| `paths.py`, `logging_setup.py` | emplacements portables et journalisation avec rotation |
| `release_channel.py` | classification d'un tag (`stable` ou `beta`) utilisee par la release |

## Flux principal d'un cycle

```
run_loop() [watcher.py]
  |
  |-- chargement config + signature
  |-- demarrage tableau de bord + icone (sauf --once)
  |-- verification de la politique de mise a jour (si activee)
  |     REQUIRED au-dessus de la version locale -> mode bloque, run --once code 3
  |     sinon -> annoncer la migration eventuelle et poursuivre
  |
  |-- planning : hors plage ou creneau deja signe ?
  |     oui -> attendre la prochaine ouverture (tranches de 5 s)
  |
  |-- CesarSession.open(headless=...) [cesar.py + browser.py]
  |
  v
boucle toutes les poll_interval secondes
  |
  |-- planning : fin de plage ou creneau deja signe ?
  |     oui -> fermer le navigateur, attendre, rouvrir
  |
  |-- session.check()  -> AttendanceSignal | None
  |     - rechargement du tableau de bord
  |     - recherche du bouton d'emargement
  |     - identifiant stable de l'emargement
  |
  |-- aucun signal -> attendre le cycle suivant
  |
  |-- signal deja traite (state.seen) -> ignorer
  |
  |-- handle_signal() : dry-run, auto, ou confirmation utilisateur
  |     PRESENT -> sign_with_visibility()
  |     ABSENT  -> marquer comme traite
  |     SANS REPONSE -> reessayer apres prompt_retry
  |
  |-- sign_with_visibility() : session.sign(points)
  |     - eventuellement bascule en navigateur visible
  |     - trace, validation, lecture de la confirmation
  |
  |-- succes -> state.mark(), compteurs, notification
  |-- erreur Cesar -> compteur d'erreurs, nouvelle tentative plus tard
  |     (3 erreurs consecutives -> session.restart())
  v
attendre poll_interval puis recommencer
```

Chaque cycle repart d'une page rechargee : c'est ce rafraichissement qui fait
apparaitre le bouton d'emargement. La detection arrive donc au pire un
`poll_interval` apres l'ouverture par le formateur.

## Etat et deduplication

`state.py` conserve un fichier JSON dans le dossier de donnees :

- les cles d'emargements deja traites, avec TTL (`dedupe_ttl`) ;
- les creneaux deja signes, pour ne pas relancer la surveillance avant le
  suivant, meme apres un redemarrage ;
- des compteurs et dates pour le tableau de bord.

Un emargement sans reponse n'est pas marque : il revient apres `prompt_retry`.
Repondre "Absent" le marque comme traite pour la duree du TTL.

## Tableau de bord et onboarding

Les deux interfaces sont des pages HTML servies localement par
`ThreadingHTTPServer`, avec un jeton aleatoire et une ecoute limitee a
`127.0.0.1`. `window.py` les affiche dans une fenetre pywebview, ou dans le
navigateur si le moteur natif manque.

- `status_server.py` expose l'etat courant et les actions (test de notification,
  verification et installation d'une mise a jour, reconfiguration, logs, arret).
  Le port et le jeton sont publies dans `runtime.json` pour que `ui/` et la CLI
  puissent s'y connecter.
- `setup_server.py` porte l'onboarding : test de connexion CESAR, capture ou
  import de signature, planning, test de notification, demarrage automatique.

## Mises a jour

`updates.py` interroge les releases GitHub et filtre les candidates selon
`updates.channel` (`stable` ou `beta`). Le canal explicite de la configuration
reste prioritaire ; sans valeur explicite, il suit la version installee.

Chaque release peut porter deux marqueurs dans son corps, ajoutes en tete par le
workflow de release :

```
CHECKMATE-MIGRATION: 0
CHECKMATE-REQUIRED: 0
```

`0` signifie non applicable. Sinon, la valeur est une raison courte conservee
dans `Release.migration_reason` ou `Release.required_reason`.

`update_policy()` produit un `UpdatePolicy` qui contient :

- `latest` : la version la plus recente du canal courant ;
- `required` : la release `REQUIRED` la plus recente au-dessus de la version
  locale ;
- `migration` : la premiere release `MIGRATION` au-dessus de la version locale ;
- `available` : vrai si `latest` est plus recente que la version locale ;
- `install_target` : `migration` si une etape intermediaire existe, sinon
  `latest` si une mise a jour est disponible.

Au demarrage, `watcher.py` evalue cette politique avant d'ouvrir CESAR. Si
`required` existe, la surveillance ne demarre pas : notification, icone en
attention requise, tableau de bord en mode bloque et code de sortie 3 pour
`run --once`. L'installation et l'arret restent accessibles depuis le tableau de
bord. Une erreur reseau ou une verification desactivee laisse l'application
fonctionner.

`self_update.prepare()` telecharge `install_target`, verifie le SHA256, puis
`self_update.py` delegue l'installation a un processus detache : installeur Inno
sous Windows, script shell sous Linux. Une migration est donc installee avant la
cible finale. Apres redemarrage, elle sort de la fenetre de mise a jour et
l'etape suivante peut etre proposee.

Cote publication, `.github/release-markers.txt` porte les deux valeurs de la
prochaine release. Le workflow refuse un marqueur absent ou vide. Un marqueur
non nul passe par l'environnement GitHub `release-manual`, qui exige une
approbation humaine. Les valeurs `0`/`0` passent par `release-auto`. La
configuration exacte des environnements est documentee dans
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#environnements-github-de-publication).

## Frontiere de securite

- Le mot de passe ne passe jamais dans les logs ; il vient du trousseau ou de
  `CHECKMATE_PASSWORD`.
- Les serveurs locaux n'ecoutent que sur `127.0.0.1` et exigent un jeton.
- La signature est stockee en points, pas en image.
- Aucun secret n'est ecrit dans la configuration par defaut.
