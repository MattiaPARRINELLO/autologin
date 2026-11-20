# Emulateur CESAR

Faux CESAR Emineo local, autonome et sans dependance, pour tester le watcher
comme si c'etait le vrai site. Il ne fait aucun appel reseau.

## Lancer

```bash
python3 emulator/server.py --port 8787
```

Identifiants par defaut : `demo` / `demo`.

| URL | Role |
|-----|------|
| `/connexion` | formulaire de connexion, cookie de session |
| `/` | tableau de bord, bouton d'emargement affiche seulement si ouvert |
| `/admin` | ouvrir, fermer, reinitialiser l'emargement |
| `/api/state` | etat courant en JSON |
| `POST /api/attendance/open` | ouvre une session d'emargement |
| `POST /api/attendance/close` | ferme l'emargement |
| `POST /api/attendance/reset` | remet tout a zero |
| `POST /api/signature` | enregistre la signature `{points: [...]}` |

Le bouton est rendu cote serveur : un onglet deja ouvert ne le voit apparaitre
qu'apres un rafraichissement, exactement comme sur le vrai CESAR. C'est ce que
le watcher teste en rechargeant la page a chaque cycle.

## Brancher le watcher dessus

```bash
cp emulator/watcher.toml ~/.config/checkmate-watcher/emulator.toml
# signature si tu n'en as pas encore
cd watcher && uv run checkmate-watcher --config ~/.config/checkmate-watcher/emulator.toml capture
# lancer
uv run checkmate-watcher --config ~/.config/checkmate-watcher/emulator.toml run -v
```

Puis ouvre `http://127.0.0.1:8787/admin` et clique sur "Ouvrir l'emargement".
Au cycle suivant, le watcher detecte le bouton, affiche la notification, et si
tu acceptes, ouvre une fenetre visible uniquement pour signer, puis la referme.
L'etat passe a "signe" dans `/admin`.

## Test automatique complet

Le test d'integration lance l'emulateur, ouvre l'emargement, execute le watcher
en mode automatique et verifie que la signature est bien enregistree :

```bash
CHECKMATE_E2E=1 uv run --project watcher pytest watcher/tests/test_emulator_e2e.py -v
```

Il est ignore par defaut car il demande Chromium et ouvre un navigateur. La CI
le lance automatiquement dans le job `E2E emulateur`.
