# Politique de sécurité

## Versions prises en charge

Seules les versions publiées depuis `main`, sur le canal stable, reçoivent des
correctifs de sécurité. Les préversions du canal `beta` sont fournies pour les
tests et peuvent ne pas être corrigées.

| Version | Support |
| ------- | ------- |
| 0.6.x stable | oui |
| 0.6.x beta | au mieux, sans engagement |
| 0.5.x et antérieures | non |

## Signaler une faille

N'ouvre pas d'issue publique pour une faille de sécurité. Utilise le signalement
privé de GitHub :

https://github.com/MattiaPARRINELLO/autologin/security/advisories/new

Si le signalement privé n'est pas disponible, contacte le mainteneur par
message direct sur GitHub en décrivant le problème sans publier de détail
exploitable.

## Contenu du rapport

- version et plateforme concernées ;
- description de la faille et impact possible ;
- étapes de reproduction minimales ;
- preuve de concept si elle existe, sans donnée personnelle réelle ;
- correctif proposé si tu en as un.

## Traitement

Le mainteneur accuse réception dès que possible, puis indique si le rapport est
accepté et quel correctif est envisagé. Le délai dépend de la disponibilité et
de la gravité. Merci de laisser un temps raisonnable avant toute divulgation
publique.

## Périmètre

Sont concernés : le watcher Python, l'émulateur de test, les scripts de
packaging et les workflows de release. Les problèmes liés au site
CESAR lui-même ne relèvent pas de ce dépôt.
