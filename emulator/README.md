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

## Servir un scenario capture

Le mode `--scenario` remplace les pages generees par des pages capturees, pour
reproduire le vrai DOM de CESAR sans toucher au site :

```bash
python3 emulator/server.py --port 8787 --scenario emulator/scenarios/cesar-simplifie
```

Un scenario est un dossier autonome :

| Fichier | Role |
|---------|------|
| `scenario.json` | manifeste : route vers page, par etat d'emargement |
| `pages/*.html` | pages capturees, une variante par etat |
| `harness.js` | script injecte avant `</body>` pour rebrancher les interactions |
| `assets/` | CSS, JS, polices, images servis sous `/assets/` |

Le manifeste associe chaque route a un fichier, ou a un fichier par etat :

```json
{
  "name": "cesar-simplifie",
  "pages": {
    "/connexion": "pages/connexion.html",
    "/": {
      "default": "pages/tableau-ferme.html",
      "open": "pages/tableau-ouvert.html",
      "signed": "pages/tableau-signe.html"
    }
  },
  "harness": "harness.js",
  "assets": "assets"
}
```

- `default` est obligatoire, `open` et `signed` sont optionnels : un etat
  absent retombe sur `default`.
- Seules les routes declarees et `/assets/` sont servies depuis le scenario.
  `/admin`, `/api/state` et `POST /api/attendance/*` restent a l'emulateur, donc
  tu peux toujours ouvrir et fermer l'emargement depuis `/admin`.
- Le JavaScript du vrai CESAR ne connait pas `/api/signature` : `harness.js`
  rebranche l'ouverture de la modale, le trace et l'enregistrement. Le jeton
  `__ATTENDANCE_CLOSE_DELAY_MS__` y est remplace par la valeur de
  `--attendance-close-delay-ms`.
- Un manifeste invalide (fichier absent, chemin hors du dossier, etat `default`
  manquant) arrete le serveur avec un message explicite.

`emulator/scenarios/cesar-simplifie` sert de reference : il reprend les
selecteurs par defaut du watcher (`.toastui-calendar-day-view`,
`.buttonPresent`, `canvas[data-written-signature-target]`,
`.swal2-html-container`) dans une structure differente des pages generees.

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
