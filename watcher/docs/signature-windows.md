# Signer l'installeur Windows

## Pourquoi

Sans signature Authenticode, SmartScreen affiche "Éditeur inconnu" au premier
lancement. Une signature reconnue affiche le nom de l'éditeur et évite cet
avertissement. Un certificat auto-signé ne suffit pas : il n'est pas dans les
magasins de confiance de Windows.

## Option A : SignPath Foundation, gratuit pour l'open source

Le dépôt est public et sous licence MIT, donc éligible au programme gratuit de
[SignPath Foundation](https://signpath.org/).

1. Créer un compte sur SignPath et demander l'accès Foundation.
2. Connecter le dépôt GitHub `MattiaPARRINELLO/autologin`.
3. Créer un projet `checkmate`, une politique de signature `release-signing` et
   une configuration d'artefact pour l'installeur.
4. Ajouter dans GitHub :
   - secret `SIGNPATH_API_TOKEN`
   - variables `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
     `SIGNPATH_POLICY_SLUG`, `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`

Le workflow pourra alors uploader l'installeur, demander la signature et
recuperer l'artefact signe. SignPath fournit aussi une GitHub Action dédiée.

## Option B : Azure Trusted Signing

Environ 10 dollars par mois, validation d'identité obligatoire, intégration
GitHub Actions correcte. Bon choix si le projet devient un produit distribué.

1. Souscription Azure, compte Trusted Signing, profil de certificat.
2. Validation d'identité.
3. Identifiants Azure dans GitHub (OIDC de préférence).
4. Action `azure/trusted-signing-action` pour signer `CheckMate.exe` puis
   l'installeur.

## Option C : certificat OV ou EV classique

200 à 400 euros par an, stockage matériel ou HSM cloud obligatoire depuis les
règles du CA/B Forum. Surdimensionné pour ce projet.

## Ce qu'il faut signer

1. `dist\CheckMate\CheckMate.exe`, avant de construire l'installeur.
2. `CheckMate-Setup-<version>.exe`, après Inno Setup.
3. Facultatif : le désinstalleur, via la directive `SignTool` d'Inno.

## Vérifier une signature

```powershell
signtool verify /pa CheckMate-Setup-0.1.1.exe
Get-AuthenticodeSignature .\CheckMate-Setup-0.1.1.exe
```

## État actuel

L'installeur construit par la CI est fonctionnel mais non signé. SmartScreen
affichera un avertissement tant qu'aucun certificat n'est branché.

## Signature avec un PFX

Si tu obtiens un certificat au format PFX :

```powershell
$env:CHECKMATE_PFX_PASSWORD = "..."
.\packaging\sign-windows.ps1 -Pfx .\certificat.pfx -Path .\dist-installer\CheckMate-Setup-0.1.1.exe
```
