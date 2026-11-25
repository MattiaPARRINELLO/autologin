# Instructions pour les agents dans ce dépôt

## Commencer ici

1. Lire [`CONTRIBUTING.md`](CONTRIBUTING.md) avant toute contribution ou release.
2. Utiliser `mcp__semble__search` avant Grep, Glob ou Read pour retrouver du code.
3. Inspecter les fichiers existants avant de modifier leur style ou leur structure.
4. Traiter les changements non commités comme du travail utilisateur potentiel.

## Périmètre

- `watcher/` : application Python publiée, CLI et tableau de bord local.
- `emulator/` : serveur CESAR de test.
- `ui/` : interface Rust expérimentale, hors release.
- `.github/workflows/` : CI, sécurité et publication.

## Vérifications locales

Depuis `watcher/` :

```bash
uv lock --check
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
```

Tests navigateur de bout en bout, optionnels en local mais exécutés en CI :

```bash
CHECKMATE_E2E=1 uv run pytest -q tests/test_emulator_e2e.py
```

Pour une modification de documentation :

```bash
python3 scripts/check_doc_versions.py
```

Pour `ui/` :

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

## Branches et commits

- Partir de `main` pour une nouvelle contribution.
- Ne jamais pousser directement sur `main` et ne jamais réécrire son historique.
- Commits granulaires au format Conventional Commits.
- Une modification vérifiée ne doit pas rester non commitée en fin de travail.
- Pas de push direct sur `main`/`master`, pas de force-push, pas de PR, tag ou
  release sans accord explicite.

## Invariants de mise à jour

Le comportement utilisateur dépend de `watcher/src/checkmate_watcher/updates.py` :

- le canal explicite de `[updates]` est prioritaire ;
- sans canal explicite, une version `-beta` utilise le canal beta, sinon stable ;
- aucune mise à jour automatique ne rétrograde la version installée ;
- `CHECKMATE-REQUIRED` bloque le démarrage sous la version minimale ;
- `CHECKMATE-MIGRATION` impose l'installation de la migration avant la cible ;
- un échec réseau ne bloque pas le démarrage.

Les changements dans `config.py`, `updates.py`, `self_update.py`, `watcher.py`,
`status_server.py`, `status_ui.py` ou `tray.py` doivent vérifier ces invariants.

## Invariants de release

Avant tout tag ou toute release :

1. Mettre à jour ensemble :
   - `watcher/src/checkmate_watcher/__init__.py` ;
   - `watcher/pyproject.toml` ;
   - `watcher/uv.lock`.
2. Mettre à jour `.github/release-markers.txt` avec exactement une ligne par
   marqueur. Utiliser `0` si non applicable.
3. Lancer toutes les vérifications locales.
4. Utiliser `beta` pour un tag beta et `main` pour un tag stable.
5. Attendre le workflow `Release`. Un marqueur non nul exige l'approbation de
   l'environnement GitHub `release-manual`.
6. Vérifier les artefacts, `SHA256SUMS.txt` et le statut de prerelease.
7. Remettre les marqueurs à `0` après une release non nulle, dans le commit de
   version suivant.

Ne jamais supposer que `release-manual` est protégé : un environnement GitHub
absent est créé sans règles par GitHub. Sa configuration est documentée dans
[`CONTRIBUTING.md`](CONTRIBUTING.md#environnements-github-de-publication).

## Sécurité et documentation

- Ne jamais afficher ni committer de secret, mot de passe, jeton ou donnée
  personnelle.
- Ne jamais ajouter de capture CESAR brute au dépôt.
- Documenter tout changement de comportement dans le guide utilisateur et, si
  nécessaire, dans l'architecture.
- Tenir `CONTRIBUTING.en.md` synchronisé avec les règles de release françaises.
- Ne pas figer de numéro de release dans la documentation utilisateur.

## Références

- [`CONTRIBUTING.md`](CONTRIBUTING.md) : workflow, conventions, releases.
- [`watcher/docs/guide-utilisateur.md`](watcher/docs/guide-utilisateur.md) :
  tableau de bord, canaux, blocage et migrations vus par l'utilisateur.
- [`watcher/docs/architecture.md`](watcher/docs/architecture.md) : modules et
  politique de mise à jour.
- [`watcher/docs/depannage.md`](watcher/docs/depannage.md) : diagnostics et logs.
