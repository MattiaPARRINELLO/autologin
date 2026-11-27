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
