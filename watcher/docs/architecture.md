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

Aucun service distant de CheckMate n'intervient : le seul reseau sortant va vers
CESAR et, si les mises a jour sont activees, vers l'API GitHub des releases.

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
| `updates.py` | lecture des releases GitHub, choix du canal et verification du SHA256 |
| `self_update.py` | installation d'une mise a jour par un processus detache |
| `support.py` | archive de diagnostic sans mot de passe ni signature |
| `paths.py`, `logging_setup.py` | emplacements portables et journalisation avec rotation |
| `release_channel.py` | classification d'un tag (`stable` ou `beta`) utilisee par la release |

## Flux principal d'un cycle

```
run_loop() [watcher.py]
  |
  |-- chargement config + signature
  |-- demarrage tableau de bord + icone (sauf --once)
  |-- verification de mise a jour (si activee)
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

`updates.py` interroge les releases GitHub, filtre selon `updates.channel`
(`stable` ou `beta`) et verifie le SHA256 de l'archive. `self_update.py` delegue
l'installation a un processus detache, car le binaire ne peut pas se remplacer
pendant qu'il tourne : installeur Inno sous Windows, script shell sous Linux.

## Frontiere de securite

- Le mot de passe ne passe jamais dans les logs ; il vient du trousseau ou de
  `CHECKMATE_PASSWORD`.
- Les serveurs locaux n'ecoutent que sur `127.0.0.1` et exigent un jeton.
- La signature est stockee en points, pas en image.
- Aucun secret n'est ecrit dans la configuration par defaut.
