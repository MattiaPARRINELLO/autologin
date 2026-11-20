# Vie privée

## Compteurs d'usage anonymes

CheckMate n'a pas de compte, pas de publicité et ne suit pas ce que tu fais sur
CESAR. Il envoie seulement deux petits événements à un compteur auto-hébergé :

- `install`, une fois par ordinateur ;
- `signature`, une fois par émargement réussi.

Chaque événement contient uniquement :

- un identifiant d'installation aléatoire (32 caractères hexadécimaux), créé au
  premier lancement et stocké dans `install-id` ;
- la version de CheckMate ;
- la famille du système (`windows`, `linux`, `macos`, `other`) ;
- le nom de l'événement.

Le compteur ne stocke ni adresse IP, ni identifiant CESAR, ni mot de passe, ni
le tracé de la signature, ni le planning. Ces données servent seulement à
compter les installations et les signatures.

Tu peux désactiver ces envois à tout moment dans `config.toml` :

```toml
[analytics]
enabled = false
```

ou avec la variable d'environnement `CHECKMATE_ANALYTICS=0`. L'identifiant
d'installation reste sur ton ordinateur ; supprimer le dossier de données le
supprime aussi.

## Services contactés

- l'instance CESAR Emineo configurée dans l'assistant ;
- l'API GitHub des releases, si les mises à jour sont activées ;
- le compteur de statistiques (`main.mprnl.fr/cm-stats`), si les statistiques
  sont activées.

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
