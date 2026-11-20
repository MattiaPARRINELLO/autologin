<div align="center">
  <img src="icons/icon128.png" alt="CheckMate" width="88" />
  <h1>CheckMate</h1>
  <p><strong>Surveille CESAR et signe l'émargement sans y penser.</strong></p>

  ![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
  ![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4)
  ![Linux](https://img.shields.io/badge/Linux-systemd-FCC624)
  ![Licence](https://img.shields.io/badge/licence-MIT-green)
  ![Tests](https://img.shields.io/badge/tests-66%20passing-brightgreen)

  [Télécharger](DOWNLOAD.md) · [Documentation](watcher/docs/README.md) · [Présentation](watcher/presentation/index.html) · [Vie privée](PRIVACY.md)
</div>

---

CheckMate est une application de bureau locale pour les étudiants qui utilisent
CESAR Emineo. Elle surveille les créneaux de cours, détecte l'ouverture de
l'émargement, demande confirmation, puis rejoue la signature dans un navigateur
visible uniquement à ce moment-là.

Pas d'onglet à garder ouvert, pas de serveur, pas de télémétrie.

![Onboarding CheckMate](watcher/docs/assets/onboarding.png)

## Ce que ça fait

- surveille CESAR toutes les 10 secondes, uniquement pendant les créneaux
- affiche une notification dès que le formateur ouvre l'émargement
- demande "Je suis présent" ou "Absent"
- signe dans un navigateur visible, puis le referme
- ne vérifie plus rien une fois le créneau signé
- garde les identifiants dans le trousseau du système quand c'est possible

## Démarrage rapide

### Windows

1. Télécharge `CheckMate-Setup-0.1.0.exe` depuis la
   [pré-version desktop](https://github.com/MattiaPARRINELLO/autologin/releases/tag/watcher-0.1.0).
2. Lance l'installeur, sans droits administrateur.
3. SmartScreen peut afficher un avertissement tant que la signature de code
   n'est pas active. Clique sur "Informations complémentaires", puis
   "Exécuter quand même".
4. Suis l'onboarding dans ton navigateur.

La signature Windows sera assurée par la
[SignPath Foundation](https://signpath.org/) après acceptation du projet.

### Linux

```bash
tar -xzf CheckMate-linux-<version>.tar.gz
cd CheckMate-linux-<version>
./install.sh
```

`uv` est requis : https://docs.astral.sh/uv/getting-started/installation/

## Comment ça marche

1. **Détecte** : refresh de CESAR toutes les 10 secondes dans les créneaux.
2. **Demande** : notification et confirmation.
3. **Signe** : navigateur visible, tracé de la signature, confirmation, fermeture.

Le planning par défaut est lundi-vendredi, 09:00-12:00 et 13:30-16:30. Il se
configure dans l'onboarding.

## Vie privée

Tout reste sur l'ordinateur : identifiants, signature, session CESAR, logs. Le
seul service contacté est CESAR. Voir [PRIVACY.md](PRIVACY.md) et
[la version détaillée](watcher/docs/vie-privee.md).

## Documentation

- [Guide utilisateur](watcher/docs/guide-utilisateur.md)
- [Vie privée](watcher/docs/vie-privee.md)
- [Dépannage](watcher/docs/depannage.md)
- [Mentions légales](watcher/docs/mentions-legales.md)
- [Validation Windows](watcher/docs/windows-validation.md)
- [Signature Windows](watcher/docs/signature-windows.md) et [SignPath](watcher/docs/signpath-setup.md)
- [Présentation HTML](watcher/presentation/index.html)

## Développement

```bash
cd watcher
uv sync
uv run pytest
uv run checkmate-watcher --help
```

L'émulateur CESAR permet de tester le parcours complet sans le vrai site :

```bash
python3 emulator/server.py --port 8787
cd watcher
uv run checkmate-watcher --config ../emulator/watcher.toml run -v
```

Build :

```bash
cd watcher
bash packaging/build-linux.sh 0.1.0
powershell -File packaging/build-windows.ps1 -Version 0.1.0
```

La release GitHub se déclenche sur un tag `v*` et publie l'installeur Windows,
l'archive Linux et `SHA256SUMS.txt`.

## Ancienne extension Chrome

Le dépôt contient encore l'extension historique à la racine (`manifest.json`,
`popup.html`, `content.js`, `background.js`). Elle automatise le pointage dans
un onglet CESAR. L'application de bureau la remplace : elle ne nécessite aucun
onglet ouvert et garde le navigateur invisible pendant l'attente.

## Licence

MIT. Voir [LICENSE](LICENSE).
