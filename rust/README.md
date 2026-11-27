# Workspace Rust de CheckMate

Remplissage progressif du watcher, tranche par tranche. Le Python reste la
reference fonctionnelle jusqu'a la release `1.0.0`.

## Structure

| Crate | Role | Dependances autorisees |
|---|---|---|
| `checkmate-core` | Regles metier pures, sans entree/sortie, sans horloge, sans reseau | aucune crate du workspace |
| `checkmate-platform` | Fenetre native, icone, notifications, autostart, trousseau, chemins | `checkmate-core` |
| `checkmate-ui` | Vues GPUI, composants, navigation | `checkmate-core`, `checkmate-platform` |
| `checkmate-cli` | Binaire `checkmate` et commandes | les trois autres |

Les frontieres sont verifiees mecaniquement :

```bash
python3 scripts/check-boundaries.py
```

## Interface GPUI

La crate `checkmate-ui` utilise `gpui =0.2.2`, epingle sans branche. La
procedure de montee, les features par plateforme et les limites connues sont
dans [`watcher/docs/architecture.md`](../watcher/docs/architecture.md#interface-native-gpui).

Le binaire `checkmate-ui` lit `runtime.json` ecrit par Python et n'ecrit aucun
fichier de donnees. `CHECKMATE_HEADLESS=1` interdit toute fenetre.

## Fixtures de parite

`fixtures/parity/` contient les cas partages entre Python et Rust : `config`,
`schedule`, `release_notes`, `updates`. Chaque fichier liste des cas nommes avec
une entree et une attente, y compris les cas d'erreur.

- `watcher/tests/test_parity_fixtures.py` rejoue chaque cas avec les
  implementations Python et garantit que les fixtures decrivent le comportement
  reel.
- `crates/checkmate-core/tests/parity_fixtures.rs` verifie que le cote Rust lit
  les memes fichiers et que leur structure reste stable.

Quand un comportement change, la fixture et son test Python evoluent ensemble,
puis l'implementation Rust doit satisfaire la meme attente.

## Benchmark

`scripts/benchmark.py` mesure le demarrage du binaire, son pic de memoire, son
temps CPU et sa taille, puis compare aux budgets de
`benchmarks/budgets.json`.

```bash
cargo build --release -p checkmate-cli
python3 scripts/benchmark.py --no-build
```

Le rapport JSON est ecrit dans `benchmarks/report.json`, ignore par git. Le
script sort en code 1 des qu'un budget obligatoire est depasse.

Les metriques qui dependent de l'interface GPUI ou du moteur de detection
(`ui_startup_ms`, `rss_ui_mib`, `cpu_idle_percent`, `detection_p95_ms`) sont
declarees `required: false` et signalees comme en attente. Elles deviennent
obligatoires aux tranches T1 et T4.

La memoire est lue dans `/proc/<pid>/status` (`VmHWM`) sous Linux et via
`GetProcessMemoryInfo` sous Windows, pendant une execution retenue par
`--bench-hold-ms`.

## Version

La version du workspace reste `0.0.0` tant que le binaire n'est pas publie. La
tache T0.5 alignera `Cargo.toml`, `pyproject.toml`, `__init__.py` et `BUILD`.

Le toolchain est epingle dans `rust-toolchain.toml`.

## Commandes

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
python3 scripts/check-boundaries.py
```

## Suivi

L'epic principal est [#144](https://github.com/MattiaPARRINELLO/autologin/issues/144).
La repartition des responsabilites entre Python et Rust est decrite dans
[`watcher/docs/migration-rust.md`](../watcher/docs/migration-rust.md).
