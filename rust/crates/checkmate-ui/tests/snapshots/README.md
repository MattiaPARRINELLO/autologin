# Captures de reference

GPUI 0.2.2 n'expose pas d'API de capture d'image. Les captures sont
textuelles : ecran courant, focus, version, canal, creneaux, jours,
compteurs, etape et nombre de points de signature.

Les fichiers sont suffixes par plateforme. Le contenu est identique tant que
seul le texte est fige ; les captures pixel par plateforme arriveront avec la
tranche T7, quand un backend de capture sera disponible.

Regenerer apres un changement voulu :

```bash
UPDATE_SNAPSHOTS=1 cargo test -p checkmate-ui --test render
```

Une derive inattendue fait echouer le test avec le nom du fichier.
