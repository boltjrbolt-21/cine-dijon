# Ciné Dijon

**https://boltjrbolt-21.github.io/cine-dijon/**

Une page qui répond à une seule question : **qu'est-ce que je peux aller voir, et où ?**

Tous les films à l'affiche dans les salles de l'agglomération dijonnaise, chacun résumé
en une ligne, avec les horaires regroupés par salle et le lien de réservation.

## Ce que ça contient

```
├── index.html                         la page
├── data/seances.json                  les données, régénérées automatiquement
├── icone.svg · icone-180 · icone-512  l'icône du site
├── partage.png                        la vignette affichée au partage du lien
├── scripts/collecte.py                le collecteur (Python, sans dépendance)
├── scripts/images.py                  régénère l'icône et la vignette (Pillow)
└── .github/workflows/maj-seances.yml  la mise à jour automatique
```

## Les salles suivies

| Salle | Ville | Code AlloCiné |
|---|---|---|
| Cinéville Dijon (ex-Olympia) | Dijon | `P2788` |
| Pathé Dijon | Dijon | `W2101` |
| Ciné Cap Vert | Quetigny | `P0771` |
| Le Darcy | Dijon | `P0120` |
| Eldorado | Dijon | `P0121` |
| Cinémathèque Jean Douchet | Dijon | `W2100` |

La Cinémathèque ne publie pas ses séances sur AlloCiné : sa pastille reste grisée
tant qu'aucune séance n'est trouvée, c'est normal. Pour ajouter ou retirer une salle,
modifiez la liste `CINEMAS` en haut de `scripts/collecte.py`.

## Réservation

**AlloCiné donne plusieurs liens par séance, pas un seul.** Le premier de la liste est
souvent `relay.mvtx.us`, qui aboutit systématiquement sur « Sold Out, or Not Available
Online » — vérifié salle par salle et à plusieurs dates le 21/09/2026. Le collecteur
écarte les hôtes défaillants (`HOTES_ECARTES`) et prend le lien suivant. Ne revenez
pas à `urls[0]` : c'est ce qui masquait les vraies billetteries.

État constaté au 21/09/2026 :

| Salle | Lien par séance | Vérifié |
|---|---|---|
| Pathé Dijon, Ciné Cap Vert | `s.pathe.fr` | oui, plan de salle et bonne date |
| Eldorado | `eldorado.ticketingcine.com` | oui, page de paiement de la séance exacte |
| Le Darcy | aucun | les **trois** liens d'AlloCiné sont morts → bouton **Réserver** vers TicketingCiné |
| Cinéville Dijon | aucun | bouton **Réserver** vers `dijon.cineville.fr` |

Le Darcy mérite un mot : AlloCiné en propose trois, tous cassés — `relay.mvtx.us` dit
« Sold Out », `www.cines-dijon.com` **n'existe plus** (NXDOMAIN, le cinéma a changé de
site) et `tickets.allocine.fr/portail-dijon/...` renvoie 404. La salle porte donc
`"liens_seance": False` dans `CINEMAS`, qui coupe la recherche de lien pour elle.

**Tout horaire affiché est cliquable, sans exception** — c'est la règle à préserver.
Les séances déjà commencées ne sont plus affichées du tout : les garder en grisé
revenait à proposer un horaire sur lequel on ne peut pas appuyer.

**Un seul geste dans la page :** on appuie sur l'horaire. Quand la salle ouvre sa
billetterie séance par séance, on arrive sur la séance ; sinon, sur la billetterie de
la salle, à l'adresse renseignée dans `CINEMAS` sous la clé `reservation`, et l'horaire
est à resélectionner sur place. L'attribut `title` de chaque horaire dit où il mène.

Vérifiez toute nouvelle adresse en l'ouvrant : sur ce projet, un domaine était mort et
un autre avait été racheté par un site de casino.

Attention si vous modifiez ces adresses : `cinema-eldorado.fr` **n'appartient plus au
cinéma** — le domaine sert aujourd'hui un site de casino en ligne. L'Eldorado et Le Darcy
passent par TicketingCiné, Cinéville Dijon par `dijon.cineville.fr`.

## Partage

Le lien affiche une vignette (titre, description, image `partage.png`) sur WhatsApp,
SMS, Slack et les réseaux. Ces informations viennent des balises `og:` en tête de
`index.html` : **l'adresse `og:image` doit être absolue**, donc à corriger si le
site déménage. Le bouton « Partager » de la page ouvre le partage natif sur mobile
et copie le lien sur ordinateur.

Pour régénérer l'icône et la vignette après un changement de charte :

```bash
python scripts/images.py
```

## Voir la page en local

Un simple double-clic sur `index.html` ne suffit pas : le navigateur refuse de lire
`data/seances.json` depuis un fichier local. Depuis le dossier `cine-dijon` :

```bash
python -m http.server 8000
```

puis ouvrez `http://localhost:8000`. (La page propose aussi un sélecteur de fichier
en secours si jamais le chargement échoue.)

## Régénérer les données à la main

```bash
python scripts/collecte.py --jours 10
```

Environ deux minutes : le script laisse un peu plus d'une seconde entre chaque requête
pour rester correct vis-à-vis du serveur. Il écrit `data/seances.json` **seulement**
si la collecte a réussi — en cas de problème, les anciennes données restent en place.

## Mise à jour automatique

Le workflow `maj-seances.yml` tourne deux fois par jour sur les serveurs GitHub,
relance la collecte et recommite `data/seances.json` s'il a changé. Rien à lancer
depuis votre machine.

Une seule chose à activer, une fois pour toutes : dans `Settings → Actions → General
→ Workflow permissions`, cocher **Read and write permissions**, sans quoi le robot
collecte correctement mais échoue au moment de recommiter le fichier.

Une exécution manuelle est possible à tout moment : onglet `Actions` → `Mise à jour
des séances` → `Run workflow`.

## Bon à savoir

- **Combien de jours ?** Le script interroge 10 jours, un par un. L'endpoint attend
  une **date** dans le segment `d-` (`d-2026-09-23`) : avec un simple numéro de jour,
  AlloCiné ignore le paramètre et renvoie toujours les deux jours à venir.
- **Ce que les salles publient vraiment.** Les salles art et essai (Eldorado, Le Darcy)
  affichent leur grille complète sur 10 jours. Les multiplexes ne publient que jusqu'au
  mardi — fin de la semaine cinéma — puis seulement les avant-premières et préventes
  jusqu'à ce que la grille du mercredi sorte, en général le lundi ou le mardi.
  La page n'affiche que les jours réellement disponibles, et l'onglet
  « Toute la semaine » montre d'un coup d'œil quel film passe quel jour.
- **Si la collecte tombe en panne** (site modifié, requêtes bloquées), la page continue
  d'afficher les dernières séances connues et signale en rouge que les données ont
  plus d'un jour.
- **Source** : les horaires publiés par les salles via AlloCiné. C'est un usage
  personnel ; les données ne sont ni revendues ni redistribuées en masse.
  Vérifiez toujours l'horaire côté salle avant de vous déplacer.
