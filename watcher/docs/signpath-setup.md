# Brancher SignPath

Le workflow de release est prêt. Il construit l'installeur, l'envoie à SignPath
si les identifiants sont configurés, puis publie l'installeur signé. Sans
identifiants, il publie l'installeur non signé.

## 1. Créer la configuration SignPath

Dans SignPath, après acceptation :

- projet : `checkmate`
- politique de signature : `release-signing`
- configuration d'artefact : `windows-installer`

La configuration d'artefact doit accepter l'artefact GitHub nommé
`windows-installer`, contenant `CheckMate-Setup-*.exe`, et produire un
`CheckMate-Setup-*.exe` signé.

## 2. Secrets et variables GitHub

Secrets (Settings, Secrets and variables, Actions, Secrets) :

| Nom | Valeur |
|-----|--------|
| `SIGNPATH_API_TOKEN` | jeton API SignPath |

Variables (même page, onglet Variables) :

| Nom | Exemple |
|-----|---------|
| `SIGNPATH_ORGANIZATION_ID` | identifiant de l'organisation |
| `SIGNPATH_PROJECT_SLUG` | `checkmate` |
| `SIGNPATH_POLICY_SLUG` | `release-signing` |
| `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | `windows-installer` |

Tant que `SIGNPATH_PROJECT_SLUG` est vide, l'étape SignPath est ignorée et la
release publie l'installeur non signé.

## 3. Publier une version

```bash
git tag v1.0.0
git push origin v1.0.0
```

Le workflow :

1. construit `CheckMate-Setup-1.0.0.exe`
2. l'uploade comme artefact `windows-installer`
3. demande la signature à SignPath
4. uploade l'artefact `windows-installer-signed`
5. publie en priorité l'installeur signé, sinon le non signé
6. calcule `SHA256SUMS.txt`

## 4. Vérifier

```powershell
signtool verify /pa CheckMate-Setup-1.0.0.exe
Get-AuthenticodeSignature .\CheckMate-Setup-1.0.0.exe
```

La page de téléchargement mentionne déjà la SignPath Foundation :
`DOWNLOAD.md`.

## 5. Signer aussi le binaire interne

Pour supprimer l'avertissement au lancement de l'application installée, ajoute
`CheckMate.exe` à la configuration d'artefact SignPath, ou fais une seconde
demande de signature sur le bundle avant Inno Setup. La version actuelle signe
l'installeur, ce qui couvre le téléchargement et l'installation.
