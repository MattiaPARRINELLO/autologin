## Description

Décris le changement et le problème qu'il résout.

## Type de changement

- [ ] Correction de bug
- [ ] Nouvelle fonctionnalité
- [ ] Documentation
- [ ] CI, outillage ou packaging
- [ ] Refactorisation sans changement de comportement

## Vérifications

- [ ] `uvx ruff check src tests` passe dans `watcher`
- [ ] `uvx ruff format --check src tests` passe dans `watcher`
- [ ] `uv run pytest -q` passe dans `watcher`
- [ ] La documentation est mise à jour si le comportement change
- [ ] Aucun secret, identifiant ou donnée personnelle n'est ajouté

## Impact

Précise les plateformes concernées (Windows, Linux), les canaux (stable, beta)
et toute migration de configuration nécessaire.

## Divulgation IA

Si le contenu a été produit avec un assistant IA, indique-le explicitement ici et
précise ce qui a réellement été exécuté, testé ou vérifié par un humain.
