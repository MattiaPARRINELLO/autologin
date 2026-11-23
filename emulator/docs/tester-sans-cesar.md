# Tester avec une capture CESAR

Une capture est un parcours CESAR reel fige sur disque : pages HTML, ressources,
HAR et trace. L'emulateur la sert comme un faux CESAR local, donc le watcher se
teste contre le vrai DOM, sans creneau et sans risque de signer une presence
reelle.

A utiliser quand l'emulateur genere ne suffit pas : selecteurs du vrai site,
taille et style reels du canvas, structure reelle de la popup. Pour un simple
cycle de surveillance, `emulator/server.py` sans `--scenario` suffit.

## 1. Servir la capture

Depuis la racine du depot :

```bash
python3 emulator/server.py --port 8787 --open --scenario watcher/captures/2026-11-23
```

`--open` ouvre l'emargement au demarrage, pour que la page `open` du scenario
soit servie. Sans `--open`, le tableau de bord reste dans l'etat `default`.

L'etat se pilote aussi a chaud :

```bash
curl -X POST http://127.0.0.1:8787/api/attendance/open
curl -X POST http://127.0.0.1:8787/api/attendance/close
curl -X POST http://127.0.0.1:8787/api/attendance/reset
curl -s http://127.0.0.1:8787/api/state
```

## 2. Configurer le watcher pour la capture

Le fichier `emulator/watcher.toml` pointe deja sur `http://127.0.0.1:8787`.
Pour un cycle entierement automatique, copie-le et passe `auto_sign = true` :

```bash
cat > /tmp/capture.toml <<'EOF'
[cesar]
base_url = "http://127.0.0.1:8787"
login_path = "/connexion"
dashboard_path = "/"
username = "demo"
password = "demo"

[schedule]
enabled = false

[watcher]
poll_interval = 15
auto_sign = true
auto_sign_delay = 0
headless = true
visible_on_sign = false
profile_dir = "/tmp/checkmate-capture-profile"
state_file = "/tmp/checkmate-capture-state.json"

[signature]
file = "~/.config/checkmate-watcher/signature.json"

[updates]
enabled = false

[analytics]
enabled = false

[notifications]
enabled = false
EOF
```

Avec `auto_sign = false`, garde `emulator/watcher.toml` : le watcher notifie et
attend ta confirmation, ce qui permet de regarder la fenetre de signature.

## 3. Lancer un cycle

```bash
cd watcher
uv run checkmate-watcher --config /tmp/capture.toml run --once -v
```

Sortie attendue quand tout va bien :

```
connexion reussie
bouton d'emargement detecte : Emargement ouvert
signature rejouee : 235 points, canvas 322x152
confirmation du site : Votre presence a bien ete prise en compte
bouton d'emargement disparu apres 0.6 s
presence signee
```

Verifie l'etat cote emulateur :

```bash
curl -s http://127.0.0.1:8787/api/state
```

`"signed": true` et `signature_points` superieur a 2 signifient que la
signature a bien ete enregistree. Le nombre de points vient de ta signature, pas
du scenario. Pour rejouer, `reset` puis `open`.

## 4. Reproduire un bug

Le scenario est fait pour etre modifie. Les leviers utiles, dans
`watcher/captures/<date>/` :

- `harness.js` : ouverture de la popup, ecoute des evenements sur le canvas,
  envoi sur `/api/signature`. C'est la que se simulent un clic qui interrompt le
  trace, une popup qui bouge, ou un canvas qui ignore une famille d'evenements.
- `pages/*.html` : structure et attributs reels. Modifie une taille de canvas,
  un `z-index`, un `overflow` pour retrouver une condition d'affichage.
- `scenario.json` : quelle page sert chaque etat (`default`, `open`, `signed`).

Exemple de reproduction d'un canvas qui ignore les evenements souris : dans
`harness.js`, remplace les ecoutes `pointer*` du canvas par des ecoutes
`mouse*` uniquement, puis relance le cycle. Si le watcher signe quand meme, le
repli par evenements DOM fonctionne ; s'il echoue, tu as la condition du bug.

Pour voir le bug tel qu'il apparait chez toi, fais tourner ce meme scenario sur
**Windows** : copie `emulator/`, le dossier de capture et lance les memes
commandes. Le rendu, le DPI et les polices viennent du systeme, pas de la
capture.

## 5. Ce que la capture ne remplace pas

- Le JavaScript du site : `harness.js` le remplace. Les animations de popup et
  les gestionnaires d'evenements de CESAR ne sont pas rejoues a l'identique.
- Les ressources non capturees : polices, icones et bundles charges
  dynamiquement renvoient 404. Sans effet sur la detection et la signature,
  mais la page n'est pas pixel pour pixel.
- L'anti-rejeu du site : la capture est figee, elle ne prouve pas qu'un
  correctif marchera sur la vraie page.

## 6. En faire un test automatique

Le scenario capture peut devenir une fixture versionnee, a condition d'etre
assaini :

1. verifie qu'aucune donnee personnelle ne reste (`grep` sur le nom,
   l'identifiant, l'UUID) ;
2. deplace le dossier dans `emulator/scenarios/<nom>/` ;
3. ajoute un test dans `watcher/tests/test_emulator_e2e.py`, sur le modele de
   `test_une_capture_de_cesar_devient_un_scenario_jouable` (lancement avec
   `--scenario`, `run_loop(..., once=True)`, verification de `signed`).

`captures/` reste ignore par git : une capture brute ne se commite jamais. Le
HAR assaini n'a plus de cookies, de jetons ni de corps de requete, mais
`trace.zip` contient les formulaires saisis : garde-le local et supprime-le
quand tu n'en as plus besoin.
