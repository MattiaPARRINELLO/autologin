# Contribuer a CheckMate

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

`main` exige une pull request et refuse les poussees directes. Commande utilisee
pour appliquer la protection (necessite les droits d'administration du depot) :

```bash
gh api -X PUT repos/MattiaPARRINELLO/autologin/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Le compte de revues est a zero pour permettre a un mainteneur seul de fusionner
sa propre pull request ; la pull request et l'interdiction de poussee directe
restent obligatoires. `beta` n'est pas protegee de la meme facon pour ne pas
bloquer le travail courant.

## Verification locale

```bash
cd watcher
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
```
