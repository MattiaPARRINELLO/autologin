# Notices de tiers

## Protocole de détection CESAR

Le transport HTTP de CheckMate s'appuie sur le protocole identifié par
[Ralex91/SaladeCesar](https://github.com/Ralex91/SaladeCesar), branche
`feat/attendance-signature`, commit de référence `1d7e2a7` du 2026-11-24.

L'auteur a autorisé la reprise et l'adaptation de ce protocole. CheckMate
réimplémente notamment la connexion avec jeton CSRF, l'étape CVEC et la lecture
des attributs JSON du calendrier CESAR.

Les éléments suivants ne sont pas repris :

- la désactivation de la vérification TLS ;
- les secrets, fichiers `.env` et jetons d'exemple du projet source ;
- toute logique de signature HTTP, la signature restant rejouée dans Chrome.

`curl_cffi` est utilisé comme client HTTP avec profil Chrome afin de conserver
une empreinte réseau cohérente. Cette imitation ne garantit pas une
indistinguabilité absolue et ne remplace pas le repli navigateur.
