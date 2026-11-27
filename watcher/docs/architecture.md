# Architecture du watcher

Cette page decrit l'application Python de `watcher/` : ses modules, le flux d'un
cycle de surveillance et les frontieres entre les composants. Elle sert de carte
avant de lire le code.

## Vue d'ensemble

Le watcher est un processus unique qui :

1. charge la configuration TOML et la signature ;
2. decide si la surveillance est autorisee par le planning ;
3. detecte les emargements en HTTP leger avec `curl_cffi`, ou dans Chromium en
   repli ;
4. demande confirmation a l'utilisateur quand un emargement apparait ;
5. ouvre Chrome uniquement pour signer, memorise l'emargement traite et attend
   le cycle suivant ;
6. expose un tableau de bord local (HTTP sur `127.0.0.1`) et une icone de
   notification tant qu'il tourne.

Aucun service CheckMate n'intervient dans la surveillance : le seul reseau
sortant va vers CESAR, vers l'API GitHub des releases si les mises a jour sont
activees, vers le compteur de statistiques anonymes si `[analytics]` reste
active, et vers les messages diffuses si `[broadcast]` reste active.

## Carte des modules

| Module | Role |
|--------|------|
| `cli.py` | point d'entree `checkmate-watcher` : commandes `run`, `setup`, `status`, `capture`, `self-test`, `update`, `support-bundle`, etc. |
| `watcher.py` | boucle de surveillance `run_loop`, orchestration des decisions et des signatures |
| `cesar.py` | `CesarSession` : navigation Playwright allégée, connexion, detection de l'emargement, trace de la signature |
| `http_session.py` | `HttpCesarSession` : login CSRF/CVEC, detection HTTP, cookie partage et signature a la demande |
| `browser.py` | choix du navigateur : config, Chromium de Playwright, navigateur systeme |
| `config.py` | chargement et validation du TOML (`[cesar]`, `[watcher]`, `[schedule]`, `[notifications]`, `[updates]`, `[selectors]`) |
| `remote_selectors.py` | correction des selecteurs CESAR à distance, validation stricte et cache local |
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
| `release_notes.py` | resumes versionnes des nouveautés et micro-resumes affiches après les mises a jour stables majeures ou mineures |
| `analytics.py` | compteurs d'usage anonymes : installation et signature |
| `broadcast.py` | messages diffuses par le mainteneur, derniers vus retenus dans l'etat |
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
  |     puis -> ouvrir le resume des nouveautés si une release stable importante change
  |-- messages diffuses : premier contact memorise sans notifier
  |     puis verification en tache de fond toutes les 5 min, meme en pause
  |     notification des identifiants jamais vus
  |
  |-- planning : hors plage ou creneau deja signe ?
  |     oui -> attendre la prochaine ouverture (tranches de 5 s)
  |
  |-- session = HttpCesarSession ou CesarSession [transport]
  |     HTTP -> login curl_cffi, cookie persistant, aucun Chromium
  |     navigateur -> CesarSession.open(headless=...)
  |
  v
boucle toutes les poll_interval secondes
  |
  |-- planning : fin de plage ou creneau deja signe ?
  |     oui -> fermer la session, attendre, rouvrir
  |
  |-- session.check()  -> AttendanceSignal | None
  |     HTTP -> GET du tableau de bord, parsing des attributs calendrier
  |     navigateur -> rechargement et recherche du bouton
  |     erreur HTTP -> notification et repli navigateur
  |     identifiant stable de l'emargement
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
  |     - HTTP -> ouvrir Chrome et injecter PHPSESSID
  |     - eventuellement bascule en navigateur visible
  |     - trace, validation, lecture de la confirmation
  |     - overlay visuel non interactif retire avant validation
  |     - HTTP -> refermer Chrome apres la signature
  |
  |-- succes -> state.mark(), compteurs, notification
  |-- erreur Cesar -> compteur d'erreurs, nouvelle tentative plus tard
  |     (3 erreurs consecutives -> session.restart())
  v
attendre poll_interval puis recommencer
```

En mode HTTP, la detection lit les attributs JSON du calendrier dans la reponse
CESAR. La signature reste toujours rejouee dans Chrome avec la meme session :
le cookie `PHPSESSID` est injecte dans le contexte Playwright juste avant la
signature. Le transport `browser` reste disponible et sert de repli automatique
si le HTTP echoue, est bloque ou renvoie une page inattendue. Ce chemin demande
une réponse fraîche à chaque navigation, bloque les images, polices, médias et
domaines d'analytics, tout en conservant CSS et scripts. Des arguments Chromium
suppriment aussi le GPU, l'audio et les tâches réseau d'arrière-plan.

Au demarrage, `remote_selectors.py` charge un fichier JSON HTTPS heberge dans le
depot. Seules des listes de selecteurs non vides sont acceptees, sans URL ni
JavaScript. Le fichier valide est mis en cache ; en cas de panne reseau, CheckMate
utilise ce cache puis les selecteurs locaux. Les valeurs distantes passent avant
les valeurs locales pour permettre une reprise d'urgence. La variable
`CHECKMATE_REMOTE_SELECTORS=0` desactive ce mecanisme.

## Etat et deduplication

`state.py` conserve un fichier JSON dans le dossier de donnees :

- les cles d'emargements deja traites, avec TTL (`dedupe_ttl`) ;
- les creneaux deja signes, pour ne pas relancer la surveillance avant le
  suivant, meme apres un redemarrage ;
- des compteurs et dates pour le tableau de bord.

Un emargement sans reponse n'est pas marque : il revient apres `prompt_retry`.
Repondre "Absent" marque le creneau comme termine avec le motif `absent` :
la surveillance reprend au creneau suivant, meme apres un redemarrage.

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

`release_notes.py` compare la version precedente a la version courante. Seule une
release stable majeure ou mineure, ou le passage d'une beta a sa version stable,
avec un resume present dans le fichier JSON embarque ouvre la fenetre des
nouveautes. La version lancee et la version fermee sont conservees dans `state.py`.
Le tableau de bord recoit le resume dans `/api/status`, puis l'action
`dismiss-release` memorise sa fermeture. Le popup est rendu dans `status_ui.py`
avec focus piege, touche Echap et mouvement reduit.

Le champ `teaser` du meme fichier fournit un micro-resume court. Le workflow de
release l'ajoute aux notes GitHub avec le marqueur `CHECKMATE-SUMMARY`. Les
versions deja installees lisent donc ce marqueur via l'API GitHub et peuvent
afficher la raison de mettre a jour avant l'installation, sans attendre d'embarquer
le nouveau resume complet.

Cote publication, `.github/release-markers.txt` porte les deux valeurs de la
prochaine release. Le workflow refuse un marqueur absent ou vide. Un marqueur
non nul passe par l'environnement GitHub `release-manual`, qui exige une
approbation humaine. Les valeurs `0`/`0` passent par `release-auto`. La
configuration exacte des environnements est documentee dans
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#environnements-github-de-publication).

## Migration Rust

La reecriture 1.0 est suivie par tranches dans l'epic
[#144](https://github.com/MattiaPARRINELLO/autologin/issues/144). La repartition
des responsabilites entre Python et Rust, ressource par ressource et tranche par
tranche, est fixee dans [migration-rust.md](migration-rust.md).

## Frontiere de securite

- Le mot de passe ne passe jamais dans les logs ; il vient du trousseau ou de
  `CHECKMATE_PASSWORD`.
- Le fichier `http-cookies.json` contient la session CESAR, est limite aux
  permissions `600` et n'est jamais affiche dans les logs ou les notifications.
- Les serveurs locaux n'ecoutent que sur `127.0.0.1` et exigent un jeton.
- La signature est stockee en points, pas en image.
- Aucun secret n'est ecrit dans la configuration par defaut.

## Interface native GPUI

La coquille Rust de la tranche T1 lit l'API locale Python et n'ecrit aucun
fichier de donnees.

### Version epinglee

`gpui` est declare dans `rust/Cargo.toml` avec une version exacte,
`=0.2.2`, et jamais une branche ni `main`. Les features dependent de la cible :

| Cible | Features | Raison |
|---|---|---|
| Linux, FreeBSD | `font-kit`, `x11`, `wayland` | les deux serveurs d'affichage |
| Windows | `font-kit`, `windows-manifest` | manifeste DPI et execution |
| macOS | `font-kit` | backend natif |

`libc` est verrouille a `0.2.189` et `mio` a `1.2.4` dans
`rust/Cargo.lock`. La raison est une incompatibilite transitive :
`gpui 0.2.2` tire `xattr 0.2.3`, qui utilise `libc::ENOATTR`, retire des
definitions Linux dans `libc 0.2.190` ; et `mio 1.2.5` exige justement
`libc >= 0.2.190`. Les deux verrous disparaitront avec une version de GPUI
qui ne depend plus de cette combinaison.

### Procedure de montee

1. Changer la version dans `rust/Cargo.toml`, jamais la source git.
2. `cargo update -p gpui` puis verifier `cargo tree -p checkmate-ui`.
3. `cargo test` : les tests `gpui::test` couvrent le tableau de bord, les cinq
   etapes de l'assistant et les fenetres modales.
4. Comparer les captures textuelles de `rust/crates/checkmate-ui/tests/` avec
   le rendu courant. Une difference inattendue est un echec, pas une mise a
   jour automatique.
5. Verifier la matrice : Linux X11, Linux Wayland, Windows, puis macOS
   manuellement. La CI couvre Linux et Windows, macOS reste manuel jusqu'a la
   tranche T7.
6. Verifier le mode sans fenetre : `CHECKMATE_HEADLESS=1 cargo run -p
   checkmate-cli --bin checkmate-ui` ne doit creer aucune fenetre ni paniquer.
7. Consigner la version et les ecarts dans cette section.

### Empaquetage

Le binaire s'appelle `checkmate-ui`. Il lit `runtime.json` sans argument et
Python le lance quand il est present (`native_ui.py`). Il est livre dans le
meme paquet que l'application Python. Si le binaire manque, Python journalise
l'erreur et retombe sur pywebview puis le navigateur : ce repli protege d'un
paquet incomplet, ce n'est pas un drapeau opt-in. L'empaquetage des installeurs
est suivi dans
[#235](https://github.com/MattiaPARRINELLO/autologin/issues/235).

### Accessibilite

GPUI 0.2.2 n'expose aucune API d'accessibilite : pas de role, pas de libelle
de lecteur d'ecran. La coquille fournit donc une navigation clavier complete,
un ordre de tabulation explicite, des raccourcis, la fermeture par Echap et des
libelles internes verifiables par test. L'exposition aux lecteurs d'ecran est
bloquee en amont et suivie dans
[#163](https://github.com/MattiaPARRINELLO/autologin/issues/163).
