# Frontiere Python et Rust pendant la migration 1.0

Ce document fixe qui possede chaque ressource pendant la reecriture. Il complete
l'epic [#144](https://github.com/MattiaPARRINELLO/autologin/issues/144) et la
tranche T0.

## Regles

1. **Un seul ecrivain par ressource.** Un fichier mutable a exactement un
   proprietaire a un instant donne. Les autres processus le lisent seulement.
2. **Python reste la reference** jusqu'a la tranche qui transfere la ressource.
   Rust ne prend jamais une ressource par effet de bord.
3. **Une bascule est un commit dedie**, avec un test de migration et un retour
   arriere possible tant que la ressource est partagee.
4. **La compatibilite des fichiers est obligatoire** jusqu'a la tranche T6.
   La suppression d'un ancien format passe par le marqueur
   `CHECKMATE-MIGRATION`.
5. **Aucune double ecriture.** Si les deux implementations doivent lire un
   fichier, une seule ecrit, l'autre le fait via l'API locale.
6. **La coquille Rust n'execute pas la boucle** avant la tranche T4.

## Proprietaire par tranche

`L` signifie lecture seule, `E` ecriture.

| Ressource | T0 | T1 GPUI | T2 OS | T3 services | T4 moteur | T5 signature | T6 1.0 |
|---|---|---|---|---|---|---|---|
| `config.toml` | Python E | Python E | Python E | Rust E | Rust E | Rust E | Rust E |
| `state.json` | Python E | Python E | Python E | Python E | Rust E | Rust E | Rust E |
| `runtime.json`, `setup-runtime.json` et API locale | Python E | Python E, Rust L | Python E, Rust L | transition | Rust E | Rust E | supprime |
| Logs | Python E | Python E | Python E, Rust E | Rust E | Rust E | Rust E | Rust E |
| Trousseau | Python E | Python E | Python E | Rust E | Rust E | Rust E | Rust E |
| Signature et session CESAR | Python E | Python E | Python E | Python E | Python E | Rust E | Rust E |
| Mises a jour et notes | Python E | Python E | Python E | Rust E | Rust E | Rust E | Rust E |
| Icone et notifications | Python E | Python E | Rust E | Rust E | Rust E | Rust E | Rust E |
| Autostart | Python E | Python E | Rust E | Rust E | Rust E | Rust E | Rust E |
| Interface | HTML | GPUI | GPUI | GPUI | GPUI | GPUI | GPUI |
| Binaire publie | Python | Python | Python | Python | beta Rust | beta Rust | Rust |

## Points de bascule

- **T1** : `runtime.json`, `setup-runtime.json` et l'API locale restent ecrits
  par Python. La coquille Rust lit, affiche et declenche des actions. Aucune
  ecriture de fichier cote Rust. La beta publiee remplace pywebview par GPUI,
  Python reste le moteur. Le binaire `checkmate-ui` est lance par Python quand
  il est present ; s'il manque, Python journalise l'erreur et retombe sur
  pywebview puis le navigateur pour ne pas bloquer l'utilisateur.
- **T2** : l'icone, les notifications et l'autostart passent au Rust. Python
  n'affiche plus d'icone et ne cree plus de service. Le moteur continue et
  demande les notifications au binaire natif. Les journaux du moteur restent
  dans le fichier Python ; les integrations natives ecrivent leur propre
  `checkmate-native.log`. Aucun drapeau de bascule ne survit a la tranche : le
  repli Python ne s'active que si `checkmate-ui` manque ou echoue.
- **T3** : la config, l'etat, les logs, le trousseau, les mises a jour et les
  notes passent au Rust. Python lit `config.toml` et `state.json` sans les
  ecrire. La boucle et la signature restent Python.
- **T4** : la boucle, le planning, la detection HTTP et l'etat passent au Rust.
  Python ne garde que la signature, appelee comme helper. L'API locale est
  conservee jusqu'a la fin de la tranche puis retiree en T6.
- **T5** : la signature passe au CDP Rust. Python ne sert plus a rien dans le
  produit. La compatibilite des fichiers reste jusqu'en T6.
- **T6** : Python disparait de l'installeur. Le marqueur
  `CHECKMATE-MIGRATION` couvre la reprise des fichiers `0.7.x` et la procedure
  de retour arriere vers `0.7.x` est documentee.

## Etat partage

Pendant T1 a T3, Rust ne modifie ni `config.toml` ni `state.json`. Toute action
qui les change passe par `/api/action`, donc par Python. Un test de contrat sur
l'API locale detecte les divergences.

Pendant T3, Python lit `config.toml` et `state.json` au demarrage uniquement.
Un redemarrage est necessaire apres une modification faite par Rust. Ce
comportement temporaire est documente dans le guide utilisateur.

## Retour arriere

Tant que Python est embarque, la beta precedente reste le chemin de retour. A
partir de T6, le retour arriere s'appuie sur les sauvegardes automatiques des
fichiers migres et sur les artefacts `0.7.x` encore publies.
