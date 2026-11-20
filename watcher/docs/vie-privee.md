# Vie privée

## Aucun serveur

CheckMate tourne entièrement sur ton ordinateur. Il n'y a pas de compte
CheckMate, pas de backend, pas de télémétrie, pas d'analytics.

Le seul service contacté est CESAR Emineo, avec l'adresse configurée dans
l'assistant. Aucune donnée n'est envoyée ailleurs.

## Ce qui est stocké

| Donnée | Emplacement | Remarque |
|--------|-------------|----------|
| Identifiant CESAR | configuration | en clair, fichier lisible par toi seul |
| Mot de passe | trousseau du système ou fichier env | voir ci-dessous |
| Signature | `signature.json` | points du tracé, pas une image |
| Session CESAR | profil Chromium local | cookies du navigateur |
| Planning et état | configuration et `state.json` | créneaux et émargements traités |
| Logs | dossier de logs | horodatés, sans mot de passe |

Les chemins exacts s'affichent avec :

```bash
checkmate-watcher check-config
```

## Mot de passe

- **Windows et macOS** : Credential Manager ou Keychain, via le trousseau du
  système.
- **Linux** : fichier `~/.config/checkmate-watcher/env`, permissions `600`,
  utilisé par le service systemd.
- Si le trousseau est indisponible sur Windows, le mot de passe est écrit dans
  la configuration, fichier protégé par les permissions de ton compte.

Le mot de passe n'apparaît jamais dans les logs, les notifications ou les
messages d'erreur.

## Page d'onboarding

La page de configuration est servie uniquement sur `127.0.0.1`, avec un jeton
aléatoire dans l'URL. Elle ne charge aucune ressource externe et ne peut pas
être ouverte depuis une autre machine.

## Suppression

Désinstaller l'application ne supprime pas la configuration ni la signature.
Pour tout effacer :

**Windows** : supprime `%LOCALAPPDATA%\checkmate-watcher`.
**Linux** :

```bash
rm -rf ~/.config/checkmate-watcher ~/.local/share/checkmate-watcher
```

Le profil Chromium local se trouve dans le dossier de données affiché par
`check-config`.
