# Validation Windows

Objectif : valider sur une vraie machine Windows ce que la CI ne peut pas voir,
c'est-a-dire les toasts, la tache planifiee et le parcours d'onboarding.

## Preparation

1. Windows 10 ou 11, Microsoft Edge installe.
2. Installer Python 3.11+ et [uv](https://docs.astral.sh/uv/).
3. Dans le depot :

```powershell
cd watcher
uv sync
```

4. Lancer l'onboarding :

```powershell
uv run checkmate-watcher setup
```

## Parcours a valider

- [ ] la page s'ouvre dans une fenetre CheckMate native (WebView2), sans onglet
- [ ] si WebView2 est absent, repli sur le navigateur par defaut
- [ ] l'onglet ne contient aucune ressource externe
- [ ] le test de connexion CESAR reussit avec de vrais identifiants
- [ ] le mot de passe est visible dans le Gestionnaire d'identifiants Windows
- [ ] la signature se dessine correctement a la souris
- [ ] le planning propose bien 09:00-12:00 et 13:30-16:30
- [ ] le mode silencieux est coupe et le bouton "Tester la notification"
      affiche un toast Windows
- [ ] "Terminer" installe le demarrage automatique sans droits administrateur
- [ ] la valeur `CheckMate` existe dans le registre utilisateur :

```powershell
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CheckMate
```

- [ ] apres deconnexion puis reconnexion, le processus demarre sans fenetre
- [ ] les logs existent dans `%LOCALAPPDATA%\checkmate-watcher\logs`
- [ ] au debut d'un creneau, un émargement ouvert declenche la notification
- [ ] "Je suis present" ouvre Edge en visible, signe, puis referme la fenetre
- [ ] la confirmation d'emargement est bien prise en compte par CESAR

## Script automatique

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows-check.ps1
```

Le script verifie la version, lance `self-test --notify`, installe le demarrage
automatique et le relit dans le registre utilisateur. Options :

```powershell
-SkipNotification   # pas de toast
-SkipAutostart      # ne touche pas a la tache
-Exe <chemin>       # binaire ou script a tester
-Config <chemin>    # configuration a utiliser
```

## Points d'attention

- SmartScreen affichera un avertissement tant que l'executable n'est pas signe.
- Le toast peut etre masque par "Ne pas deranger" ou le mode concentration.
- Si Edge est absent, le code bascule sur Chrome, puis sur le Chromium de
  Playwright s'il est installe.
- La tache planifiee tourne dans la session de l'utilisateur : la machine doit
  etre allumee et la session ouverte pour signer.
