# Logo de ClimatSen

## Le symbole : la goutte-grille

Une goutte de pluie faite de 37 pixels, comme les pixels de 0,25° de la grille CHIRPS
sur laquelle ClimatSen détecte les pluies extrêmes. **Un seul pixel est ambre** : celui
où la pluie dépasse +2 écarts-types. Le symbole résume la méthode : la pluie, mesurée
sur une grille, dont on isole l'extrême.

## Fichiers

| Fichier | Usage |
|---|---|
| `logo-horizontal.svg` | Logo principal, fond clair : rapports, documents, site |
| `logo-horizontal-nuit.svg` | Fond indigo nuit ou sombre : diapositives, bandeaux |
| `logo-court.svg`, `logo-court-nuit.svg` | Sans signature, quand le logo fait moins de 48 px de haut (barre latérale de la plateforme) |
| `logo-vertical.svg`, `logo-vertical-nuit.svg` | Formats carrés : affiche, page de garde, écran de chargement |
| `*-mono.svg` | Une couleur (encre), pour l'impression noir et blanc et les tampons |
| `*-blanc.svg` | Blanc, sur photo ou aplat foncé quelconque |
| `symbole*.svg` | La goutte seule : avatar, filigrane |
| `favicon.svg`, `favicon-32.png`, `favicon-180.png`, `favicon-512.png` | Icône d'onglet, raccourci mobile, application |

Le texte des SVG est déjà converti en tracés : ils s'affichent à l'identique sans les
polices installées.

## Couleurs

| Nom | Hex | Rôle |
|---|---|---|
| Indigo nuit | `#1D1864` | Couleur principale : « Climat », fonds sombres, barre latérale |
| Bleu pluie | `#0284C7` | Goutte et « Sen » sur fond clair (4,1:1 sur blanc) |
| Bleu pluie clair | `#38BDF8` | Goutte et « Sen » sur fond sombre |
| Ambre extrême | `#D97706` | Le pixel extrême, sur fond clair |
| Ambre clair | `#FBBF24` | Le pixel extrême, sur fond sombre |
| Gris signature | `#5B6474` | Signature sur fond clair |
| Brume | `#C7CBF0` | Signature sur fond sombre |
| Encre | `#0F172A` | Version une couleur |

L'ambre est réservé à l'extrême : ne pas l'utiliser pour décorer. Pas de dégradé : le
logo doit pouvoir s'imprimer en une couleur.

## Typographie

* **Space Grotesk**, graisse 700 : le nom « ClimatSen ».
* **IBM Plex Sans**, graisse 500, capitales espacées : la signature « Pluies extrêmes ·
  Sénégal ».

Les deux polices sont libres (licence SIL Open Font License, Google Fonts).

## Règles

* **Zone de protection** : autour du logo, laisser au moins la largeur de deux pixels
  de la goutte (environ un quart de sa hauteur), sans texte ni bord.
* **Tailles minimales** : logo horizontal 48 px de haut (en dessous, `logo-court`),
  logo court 24 px, symbole seul 14 px.
* **Ne pas** : déformer, changer les couleurs, ajouter une ombre ou un dégradé,
  déplacer ou supprimer le pixel ambre. Dans les versions une couleur, il est évidé
  pour rester visible.
* **Nom** : toujours « ClimatSen », en un mot, C et S capitales (décision de l'équipe,
  8 octobre 2026). Ni « CLIMAT-SEN », ni « Climat-Sen », ni « Climatsen ».

## Régénérer

Les fichiers sont produits par `generer_logo.py`. Les polices ne sont pas versionnées :
télécharger `SpaceGrotesk[wght].ttf` et `IBMPlexSans[wdth,wght].ttf` depuis
github.com/google/fonts (dossiers `ofl/spacegrotesk` et `ofl/ibmplexsans`), les
renommer `SpaceGrotesk.ttf` et `IBMPlexSans.ttf` dans un dossier, puis :

```bash
python assets/branding/generer_logo.py --polices <dossier>
```

Nécessite `fonttools` et `Pillow`.
