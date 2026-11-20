# Contribuer a CheckMate

Merci de contribuer. Ce guide decrit le developpement local, les conventions de
commit, la validation automatique et le cycle de release a deux canaux.

En participant, tu acceptes le [code de conduite](CODE_OF_CONDUCT.md). Pour une
faille de securite, ne cree pas d'issue publique : suis la
[politique de securite](SECURITY.md).

## Perimetre

Le depot contient :

- `watcher/` : application Python de surveillance et d'emargement, CLI et
  tableau de bord local ;
- l'extension navigateur a la racine (`background.js`, `content.js`, `popup.*`) ;
- `emulator/` : serveur CESAR de test ;
- `.github/workflows/` : CI, securite et release.

Les propositions doivent rester dans ce perimetre. Les problemes du site CESAR
lui-meme ne sont pas traites ici.

## Environnement de developpement

Prerequis :

- Python 3.11 ou plus recent ;
- [uv](https://docs.astral.sh/uv/getting-started/installation/) ;
- Chromium, Google Chrome ou Microsoft Edge pour les tests navigateur ;
- sur Windows, Inno Setup uniquement pour construire l'installeur.

Installation et verification :

```bash
cd watcher
uv sync
uv run checkmate-watcher --version
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
```

Le test de bout en bout de l'emulateur est ignore si Chromium n'est pas
disponible :

```bash
uv run pytest -q tests/test_emulator_e2e.py
```

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

- `test (ubuntu-latest)` et `test (windows-latest)` : lint, format et tests ;
- `Secrets (gitleaks)` : detection de secrets dans le diff ;
- `Dependances (dependency-review)` : revue des dependances ajoutees ;
- `PR title` : format conventionnel du titre.

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

## Procedure de stabilisation beta vers main

1. Verifier la CI et la validation Windows sur `beta`.
2. Ouvrir une pull request `beta` vers `main`.
3. Relire le diff, puis fusionner la pull request.
4. Depuis `main`, creer le tag stable `watcher-vX.Y.Z` et le pousser :
   `git tag watcher-vX.Y.Z && git push origin watcher-vX.Y.Z`.
5. Le workflow publie l'installeur Windows, l'archive Linux et
   `SHA256SUMS.txt` en release stable.

Aucun tag ni aucune release ne doit etre cree sans validation humaine.

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
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
uv run pytest -q tests/test_emulator_e2e.py
```
