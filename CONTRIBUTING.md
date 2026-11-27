# Contribuer a CheckMate

Merci de contribuer. Ce guide decrit le developpement local, les conventions de
commit, la validation automatique et le cycle de release a deux canaux.

En participant, tu acceptes le [code de conduite](CODE_OF_CONDUCT.md). Pour une
faille de securite, ne cree pas d'issue publique : suis la
[politique de securite](SECURITY.md).

English speakers: the same rules are summarized in
[CONTRIBUTING.en.md](CONTRIBUTING.en.md).

## Licence des contributions

Le depot est publie sous licence MIT (voir [LICENSE](LICENSE)). En ouvrant une
pull request, tu acceptes que ta contribution soit publiee sous cette meme
licence MIT, sans condition supplementaire.

Aucun DCO ni accord de cession de droits (CLA) n'est demande. En soumettant une
contribution, tu certifies simplement que tu l'as ecrite ou que tu as le droit
de la soumettre.

## Perimetre

Le depot contient plusieurs surfaces. Leur statut indique quoi modifier et quoi
eviter :

| Surface | Contenu | Statut |
|---------|---------|--------|
| `watcher/` | application Python, CLI et tableau de bord local | maintenue, produit publie |
| `emulator/` | serveur CESAR de test | maintenue, outil de test |
| `ui/` | tableau de bord experimental en Rust (egui) | experimentale, hors release |
| `.github/workflows/` | CI, securite et release | maintenue |

`ui/` explore une interface native alternative ; elle n'est pas livree avec les
releases et peut casser sans preavis.

La CI compile, teste et formate `ui/` : une surface experimentale ne doit pas
pourrir en silence.

Les propositions doivent rester dans ce perimetre. Les problemes du site CESAR
lui-meme ne sont pas traites ici.

L'architecture du watcher est decrite dans
[`watcher/docs/architecture.md`](watcher/docs/architecture.md).

## Environnement de developpement

Prerequis :

- Python 3.11 ou plus recent ;
- [uv](https://docs.astral.sh/uv/getting-started/installation/) ;
- une toolchain Rust recente (edition 2024), pour `ui/` ;
- Chromium, Google Chrome ou Microsoft Edge pour les tests navigateur ;
- sur Windows, Inno Setup uniquement pour construire l'installeur.

Installation et verification :

```bash
cd watcher
uv sync
uv lock --check
uv run checkmate-watcher --version
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
```

Pour iterer sur une page reelle sans creneau,
`./scripts/dev-scenario.sh chemin/vers/capture` sert une capture et joue un cycle
complet : voir [Tester avec une capture CESAR](emulator/docs/tester-sans-cesar.md).

Les tests de bout en bout (`tests/test_emulator_e2e.py`) sont ignores par
defaut. Ils demandent Chromium et lancent eux-memes l'emulateur CESAR sur un
port libre : rien a demarrer a la main. La CI les lance avec `CHECKMATE_E2E=1` :

```bash
cd watcher
uv run playwright install chromium   # ou installe Chromium, Chrome ou Edge
CHECKMATE_E2E=1 uv run pytest -q tests/test_emulator_e2e.py
```

Interface Rust experimentale :

```bash
cd ui
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

Sans `CHECKMATE_E2E=1`, pytest ignore ces deux tests et affiche la raison
(`tests e2e desactives : definir CHECKMATE_E2E=1`). Si aucun Chromium n'est
trouve, ni celui de Playwright ni un navigateur systeme, les tests sont aussi
ignores avec `aucun Chromium disponible`.

## Capturer un parcours CESAR

Les bugs qui ne sortent qu'en conditions reelles (signature reduite a un point,
clics qui interrompent le trace, animations Windows) se reproduisent a partir
d'une capture de pages reelles. La capture est reservee aux mainteneurs : elle
demande un compte CESAR et un creneau d'emargement, donc elle se fait sur un
creneau dont la presence n'a pas d'importance.

```bash
cd watcher
uv run python -m checkmate_watcher.capture \
  --base-url https://cesar.example.fr \
  --output captures/2026-11-20 \
  --mask ".student-name" --mask "#login-display"
```

Cinq etapes sont demandees, chacune validee par Entree : page de connexion
sans se connecter, tableau de bord avec le bouton d'emargement, popup de
signature ouverte, message de confirmation affiche, puis tableau de bord apres
fermeture du message. Le script enregistre le HTML des pages, les ressources
statiques dans `assets/`, un HAR `network.har` et une trace Playwright
`trace.zip`.

Dans le vrai parcours, la page sans bouton est la meme avant le lancement de
l'emargement et apres la signature. Elle sert donc d'etat par defaut (emargement
ferme) et d'etat signe ; la page avec bouton sert d'etat « emargement ouvert ».
`pages/signature.html` et `pages/confirmation.html` sont conservees comme
reference pour ecrire le `harness.js`, mais ne sont pas servies comme routes.

Regles de stockage et de versionnement :

- `captures/` est ignore par git : une capture brute ne se commite jamais ;
- ne capture ni ne commite une page qui montre les presences d'autres eleves
  sans masquage ; `--mask` remplace le texte des selecteurs indiques ;
- l'assainissement tourne automatiquement apres la capture : references des
  ressources reecrites vers `/assets/`, formulaire de connexion ramene sur
  `/connexion`, cookies et jetons retires du HAR, corps de reponses supprimes ;
- apres assainissement, seul le quatuor `scenario.json`, `pages/`, `assets/` et
  `harness.js` peut etre versionne, et seulement comme fixture de test ;
- les captures sont datees : une page CESAR peut changer sans preavis, refais la
  capture quand les selecteurs par defaut ne trouvent plus rien.

Pour rejouer la capture :

```bash
python emulator/server.py --scenario captures/2026-11-20
cd watcher && CHECKMATE_E2E=1 uv run pytest -q tests/test_emulator_e2e.py
```

Le `harness.js` genere est un modele. Sur un vrai CESAR, adapte-le pour ouvrir
la modale, tracer et poster sur `/api/signature` : voir
`emulator/scenarios/cesar-simplifie/harness.js` pour un exemple complet.

## Workflow de contribution

1. Creer une branche depuis `main` : `feat/...`, `fix/...`, `docs/...`,
   `ci/...`, `chore/...`.
2. Developper et verifier localement.
3. Pousser la branche sur ton fork, puis ouvrir une pull request vers `main`.
4. Remplir le modele de PR, decrire le changement et lister les verifications
   executees.
5. Corriger les retours et les checks en echec. Le mainteneur fusionne apres
   revue.

Une fonctionnalite est d'abord integree a `beta`, puis stabilisee vers `main`.
Ne pousse jamais directement sur `main` et ne reecris pas son historique.

## Releases et changelog

Les notes de release GitHub sont l'historique officiel du projet. Chaque
publication stable et beta y est decrite, avec les changements et les
verifications associees.

Il n'y a pas de `CHANGELOG.md` separe : il devrait etre maintenu a la main en
plus des notes de release, et les deux finiraient par diverger. Une contribution
qui change le comportement doit donc decrire le changement dans la description
de la pull request pour qu'il se retrouve dans les notes de release.

Les notes sont regroupees par type, dans cet ordre : fonctionnalites,
corrections, documentation, dependances, maintenance. Le regroupement vient du
titre de la pull request, pas de son contenu : le job `PR title` valide le titre
conventionnel et pose le label correspondant, puis `.github/release.yml`
declare l'ordre des categories. Une pull request sans label de type ou au titre
hors convention apparait sous « Autres changements ».

La documentation ne code jamais une version de release en dur : le README pointe
sur `releases/latest` et sur le badge dynamique, et les exemples de fichiers
utilisent `<version>`. Le job `Docs versions` refuserait un numero fige.

Le parcours de support (questions, bugs, securite) est decrit dans
[SUPPORT.md](SUPPORT.md).

## Conventions de commit

Chaque commit doit rester une unite coherente et commencer par un prefixe :

`feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, `build:`,
`ci:`, `chore:`, `revert:`.

Le titre de la pull request suit le meme format. Le workflow `PR title` refuse
un titre non conforme. Exemple : `feat: ajoute le canal beta au tableau de bord`.

Un commit par unite de travail. Ne melange pas une reformatage global avec un
changement fonctionnel.

## Ce qu'une pull request doit contenir

- une description du probleme et de la solution ;
- la liste des commandes executees et leur resultat ;
- une mise a jour de la documentation si le comportement change ;
- des tests pour tout nouveau comportement ;
- aucun secret, aucune donnee personnelle, aucun identifiant reel.

## Divulgation IA

Si le contenu d'une issue, d'une PR ou d'un commentaire est ecrit par un
assistant IA, indique-le explicitement. Precise ce qui a reellement ete execute,
teste ou verifie par un humain. Ne laisse jamais croire a une validation humaine
qui n'a pas eu lieu.

## Validation automatique

Chaque pull request vers `main` doit passer :

- `test (ubuntu-latest)` et `test (windows-latest)` : lint, format et tests Python ;
- `Lockfile (uv)` : coherence entre `pyproject.toml` et `uv.lock` ;
- `UI Rust` : format, clippy et tests de `ui/` ;
- `E2E emulateur` : pointage complet contre l'emulateur, avec Chromium ;
- `Secrets (gitleaks)` : detection de secrets dans le diff ;
- `Dependances (dependency-review)` : revue des dependances ajoutees ;
- `PR title` : format conventionnel du titre ;
- `Docs versions` : aucune version de release codee en dur dans la documentation.

`main` exige aussi une revue approuvee, la resolution des conversations, une
branche a jour et un historique lineaire. Les poussees directes et les
force-push sont refuses. Le mainteneur peut utiliser son droit
d'administration pour debloquer une urgence.

## Branches et canaux

Le depot publie deux canaux de release :

- `main` : versions stables, utilisees par les installations en canal `stable`
- `beta` : prochaines versions, publiees en prerelease, pour le canal `beta`

Une fonctionnalite se developpe sur une branche de travail, puis est fusionnee
dans `beta` par une pull request. Quand la version est validee, `beta` est
fusionnee dans `main` : c'est l'etape de stabilisation. `main` ne recoit jamais
une version non testee en beta.

L'historique de `main` ne doit jamais etre reecrit : pas de force-push, pas de
rebase d'une branche deja publiee.

## Numerotation des versions

Le watcher suit SemVer (`MAJOR.MINOR.PATCH`). Une release n'incremente qu'un
seul numero a la fois.

| Changement | Numero | Exemple |
| --- | --- | --- |
| Correction de bug, message, documentation, performance, dependance | PATCH | 0.6.5 vers 0.6.6 |
| Fonctionnalite visible, nouvelle option, nouveau canal | MINOR | 0.6.6 vers 0.7.0 |
| Rupture de compatibilite | MAJOR | 1.3.0 vers 2.0.0 |

Regles de decision :

- **PATCH** : le comportement observable ne change pas, ou seul un defaut est
  corrige. Un lot de correctifs reste un PATCH, meme s'il touche plusieurs
  fichiers. C'est le choix par defaut d'une maintenance.
- **MINOR** : l'utilisateur gagne quelque chose de nouveau (ecran, option,
  canal, format de notification) sans avoir a reconfigurer quoi que ce soit. Une
  nouvelle fonctionnalite part sur `beta` en `X.Y.0-beta.N`.
- **MAJOR** : une mise a jour casse une installation existante : cle de
  configuration renommee ou supprimee, format de fichier incompatible, plateforme
  abandonnee, comportement par defaut inverse. Une MAJOR s'accompagne d'une note
  de migration dans `watcher/docs/note-mise-a-jour.md`.

Points de vigilance :

- Tant que le projet reste en `0.x`, une MINOR peut encore changer des details
  internes, mais elle ne doit jamais casser une configuration existante. La
  version `1.0.0` marque l'engagement de stabilite du format de configuration.
- Une beta garde la version cible : `0.7.0-beta.1`, `0.7.0-beta.2`, puis
  `0.7.0`. Les betas successives ne bougent pas le numero.
- Une correction urgente sur une version stable deja publiee reste un PATCH et
  ne saute pas de MINOR.
- Le changement de version se fait dans un commit dedie
  `chore: passe la version a X.Y.Z`. `VERSION` est l'unique source de verite :
  `python3 scripts/set_version.py X.Y.Z` propage la version dans `__init__.py`,
  `pyproject.toml`, `uv.lock`, `rust/Cargo.toml` et `rust/Cargo.lock`, et met a
  jour `BUILD`. `python3 scripts/set_version.py --check` verifie l'alignement,
  ce que la CI fait aussi.

## Format des tags

Un tag de release suit le prefixe `watcher-v` :

- beta : `watcher-v0.6.0-beta.1`, puis `watcher-v0.6.0-beta.2`
- stable : `watcher-v0.6.0`

Une beta est ordonnee avant sa version stable (`0.6.0-beta.1 < 0.6.0`) et deux
betas successives sont ordonnees entre elles. Les anciens tags `watcher-v0.1.3`
a `watcher-v0.6.0` restent lus comme des versions stables : le suffixe est
optionnel.

Le workflow de release refuse un tag beta construit depuis `main` et un tag
stable construit depuis `beta`. Il publie `prerelease: true` pour un tag beta et
`prerelease: false` pour un tag sans suffixe.

Le booleen `prerelease` de l'API GitHub reste la source de verite pour classer
une release deja publiee. Les releases historiques 0.1.x a 0.6.0 sont marquees
prerelease cote GitHub sans suffixe de tag, et elles restent filtrees par ce
booleen cote watcher.

## Marqueurs obligatoires de release

Chaque release doit declarer exactement une ligne par marqueur dans
`.github/release-markers.txt`, mis a jour avec le commit de version :

```
CHECKMATE-MIGRATION: 0
CHECKMATE-REQUIRED: 0
```

Les noms sont insensibles a la casse cote lecteur. Chaque ligne commence par
`CHECKMATE-`, suivi du nom, de `:` et d'une valeur. Un marqueur absent ou vide
fait echouer le workflow. `0` signifie « non applicable » et ne doit pas etre
remplace par du texte.

Exemples pour une release qui change un format et corrige une faille :

```
CHECKMATE-MIGRATION: migration du format de signature vers v2
CHECKMATE-REQUIRED: correction d'une faille de signature
```

- `CHECKMATE-MIGRATION` : la release migre des donnees ou un format de facon
  irreversible. Mettre `0` si aucune migration. Sinon, une raison courte.
  La mise a jour installe d'abord la plus ancienne migration non faite, puis
  reprend normalement apres redemarrage ; sauter cette version reste non
  supporte. Plusieurs migrations s'enchainent donc une par une.
- `CHECKMATE-REQUIRED` : version minimale obligatoire. Mettre `0` si aucune
  contrainte. Sinon, une raison courte qui sera affichee a l'utilisateur.
  Une version locale inferieure a la derniere release `REQUIRED` est bloquee
  au demarrage : le tableau de bord passe en mode bloque avec le bouton
  d'installation, l'icone signale une attention requise, et la CLI `run --once`
  sort avec le code 3. Le controle echoue ouvert si GitHub est injoignable.

Les deux marqueurs sont ajoutes en tete des notes de release par le workflow.
Si l'un des deux n'est pas `0`, la publication passe par l'environnement GitHub
`release-manual` et attend une approbation humaine. Apres une telle release,
remettre les deux valeurs a `0` dans le commit de version suivant.

### Environnements GitHub de publication

Le workflow utilise deux environnements :

- `release-auto` : aucun relecteur, pour les releases dont les deux marqueurs
  sont `0` ;
- `release-manual` : au moins un relecteur obligatoire, pour toute release avec
  un marqueur non nul.

Les deux doivent limiter le deploiement au tag `watcher-v*`. Sans cette
configuration, GitHub cree automatiquement un environnement vide au premier
passage : une release manuelle peut alors partir sans validation, ce qui rend
le garde-fou inopérant.

Configuration minimale pour un depot ou le mainteneur est seul relecteur :
desactiver « Prevent self-review », sinon il ne peut pas approuver son propre
deploiement. Avec plusieurs mainteneurs, activer cette option est preferable.

Commandes `gh api` pour creer les environnements et leur politique de tag :

```bash
UID=$(gh api user --jq .id)
REPO=MattiaPARRINELLO/autologin

gh api -X PUT "repos/$REPO/environments/release-manual" --input - <<JSON
{
  "reviewers": [{"type": "User", "id": $UID}],
  "prevent_self_review": false,
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON

gh api -X POST "repos/$REPO/environments/release-manual/deployment-branch-policies" \
  -f name='watcher-v*' -f type=tag

gh api -X PUT "repos/$REPO/environments/release-auto" --input - <<'JSON'
{
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON

gh api -X POST "repos/$REPO/environments/release-auto/deployment-branch-policies" \
  -f name='watcher-v*' -f type=tag
```

Aucun secret ni variable d'environnement n'est necessaire pour ces jobs. SignPath
reste optionnel et utilise ses propres variables et secrets documentes dans
[`watcher/docs/signpath-setup.md`](watcher/docs/signpath-setup.md).

## Procedure de release

1. Mettre a jour la version dans `watcher/src/checkmate_watcher/__init__.py`,
   `watcher/pyproject.toml` et `watcher/uv.lock` dans un commit dedie
   `chore: passe la version a X.Y.Z`.
2. Mettre a jour `.github/release-markers.txt` dans ce meme commit. Les valeurs
   sont `0` si la release n'impose ni migration ni version minimale.
3. Pour une version stable majeure ou mineure, ajouter son resume dans
   `watcher/src/checkmate_watcher/release_notes.json` : titre, resume, gains
   mesures et explications accessibles. Le champ `teaser` contient le micro-resume
   affiche avant l'installation. Une version sans resume n'ouvre pas le popup de
   nouveautes. Les betas n'ouvrent jamais ce popup.
4. Verifier localement avec les commandes de la section « Verification locale ».
5. Pour une beta, pousser `beta`, puis creer et pousser le tag
   `watcher-vX.Y.Z-beta.N` depuis `beta`.
6. Pour une stable, passer par la procedure de stabilisation ci-dessous, puis
   creer et pousser le tag `watcher-vX.Y.Z` depuis `main`.
7. Suivre le workflow `Release`. Si un marqueur est non nul, approuver le
   deploiement dans l'environnement `release-manual`.
8. Verifier la prerelease, les artefacts Windows et Linux, `SHA256SUMS.txt`, et
   tester l'installation de la version publiée.
9. Pour la release suivante, remettre les marqueurs a `0` s'ils etaient non nuls.

Aucun tag ni aucune release ne doit etre cree sans validation humaine.

## Procedure de stabilisation beta vers main

1. Verifier la CI et la validation Windows sur `beta`.
2. Ouvrir une pull request `beta` vers `main`.
3. Relire le diff, puis fusionner la pull request.
4. Depuis `main`, appliquer la procedure de release pour le tag stable
   `watcher-vX.Y.Z`.

## Protection de `main`

`main` exige une pull request, une revue et les checks ci-dessus. Commande
utilisee pour appliquer la protection (necessite les droits d'administration du
depot) :

```bash
gh api -X PUT repos/MattiaPARRINELLO/autologin/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "test (ubuntu-latest)",
      "test (windows-latest)",
      "Lockfile (uv)",
      "UI Rust",
      "E2E emulateur",
      "Secrets (gitleaks)",
      "Dépendances (dependency-review)",
      "PR title"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "required_linear_history": true
}
JSON
```

`enforce_admins` reste a `false` pour que le mainteneur puisse debloquer une
urgence sans revue. Sans ce droit, une personne seule ne pourrait pas approuver
sa propre pull request. `beta` n'est pas protegee de la meme facon pour ne pas
bloquer le travail courant.

## Verification locale

```bash
cd watcher
uv lock --check
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
CHECKMATE_E2E=1 uv run pytest -q tests/test_emulator_e2e.py
cd ..
npm ci && npm run test:syntax && npm run lint
cd ui && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
```

Les tests e2e tournent en CI, mais restent facultatifs pour une contribution
ordinaire. Ils servent a verifier le parcours complet detection puis signature
sur l'emulateur.
