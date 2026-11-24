# Note de mise à jour : installations existantes

Texte destiné aux personnes qui ont déjà installé CheckMate, à publier avec la
version qui contient les correctifs de relance (`<version>`, par exemple 0.6.4).
Remplacer `<version>` par le numéro réel avant publication.

---

## Tu utilises déjà CheckMate ? Lis ceci avant de mettre à jour

Deux bugs affectaient la mise à jour automatique : sur Linux, l'application ne
redémarrait jamais après l'installation ; sur Windows, elle restait fermée à la
fin de l'installation. Les deux sont corrigés dans la `<version>`, mais une
installation plus ancienne ne peut pas se corriger toute seule. Voici la marche
à suivre, une seule fois.

### Linux

Sur une version antérieure, l'installation lancée depuis le tableau de bord
échoue : le service s'arrête et ne revient pas. **Ne réessaie pas depuis
l'interface**, utilise le terminal :

```bash
systemctl --user start checkmate-watcher.service
checkmate-watcher update --yes
```

Si la commande n'est pas trouvée, utilise le chemin complet :

```bash
~/.local/bin/checkmate-watcher update --yes
```

L'installation se fait en arrière-plan, puis le service redémarre de lui-même.
Vérifie avec `systemctl --user status checkmate-watcher.service`.

Si tu préfères, tu peux aussi réinstaller à la main : télécharge
`CheckMate-linux-<version>.tar.gz` depuis la page des releases, décompresse-le
et lance `./install.sh`.

Tes identifiants et ta signature sont conservés dans les deux cas.

### Windows

La mise à jour depuis le tableau de bord fonctionne : elle installe la
`<version>`, dont l'installateur relance CheckMate tout seul à la fin.

Si tu mets à jour depuis une version antérieure et que l'application ne se
rouvre pas, ouvre simplement **CheckMate** depuis le menu Démarrer. À partir de
la `<version>`, ce ne sera plus nécessaire.

Pour les mises à jour suivantes, rien à faire : le tableau de bord vérifie,
installe et relance l'application.

### Vérifier la version installée

Le numéro de version est affiché en haut du tableau de bord. En ligne de
commande :

```bash
checkmate-watcher --version
```

### En cas de souci

Les journaux Linux :

```bash
journalctl --user -u checkmate-watcher -f
```

Sur Windows, ouvre le tableau de bord et consulte la section Journal. Pour un
problème qui persiste, ouvre une issue en précisant ton système et la version.
