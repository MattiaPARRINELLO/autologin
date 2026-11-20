# Statistiques CheckMate

Collecteur minimal pour compter, sans donnee personnelle :

- les installations (nouvel utilisateur, une fois par machine) ;
- les signatures reussies.

L'application envoie deux evenements a `POST /api/event` avec un identifiant
d'installation aleatoire, la version, le systeme et le nom de l'evenement. Rien
d'autre : ni identifiant CESAR, ni mot de passe, ni signature, ni adresse IP
stockee.

## Deploiement

Le collecteur tourne dans un conteneur derriere le Caddy deja present sur le
VPS, sous le chemin `https://main.mprnl.fr/cm-stats/` (meme certificat que
Homarr, aucun DNS a ajouter).

```bash
CHECKMATE_STATS_KEY="$HOME/Bureau/Oracle Server/ssh-key-2026-08-21.key" ./stats/deploy.sh
```

Le script cree `/opt/checkmate-stats`, genere le mot de passe du tableau de
bord dans `/opt/checkmate-stats/dashboard-password.txt`, ajoute la route Caddy
si besoin et verifie `/health`.

Pour utiliser un sous-domaine dedie plus tard, ajouter un bloc Caddy
`stats.mprnl.fr { reverse_proxy checkmate-stats:8099 }` puis changer
`[analytics] endpoint` dans l'application.

## Tableau de bord

`https://main.mprnl.fr/cm-stats/` (utilisateur `checkmate`, mot de passe dans le
fichier cite plus haut) :

- utilisateurs installes ;
- signatures totales et signataires uniques ;
- signatures par jour sur 30 jours ;
- repartition par version et par systeme.

## API

- `POST /api/event` : evenement (`install`, `signature`), en-tete
  `X-CheckMate-Key`.
- `GET /api/stats` : resume JSON (authentification basique).
- `GET /health` : sonde sans authentification.

## Tests

```bash
python3 -m unittest discover -s stats/tests
```

## Desactivation cote utilisateur

Dans `config.toml` :

```toml
[analytics]
enabled = false
```

ou avec la variable d'environnement `CHECKMATE_ANALYTICS=0`.
