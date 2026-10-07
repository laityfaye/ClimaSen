# Population touchée par les pluies extrêmes et communes reconstruites

*Produit le 7 octobre 2026 par `scripts/33_population_touchee_evenements.py` et `scripts/34_communes_reconstruites.py`, à partir du RGPH-5 2023 et des coordonnées des localités transmises par l'ANSD.*

## 1. Population touchée par chaque événement

**Ce que mesure le chiffre :** le nombre d'habitants **de 2023** qui vivent dans les pixels CHIRPS (environ 27 km de côté) où l'anomalie de pluie a dépassé +2σ le jour de l'événement. Pour un événement de 1985, c'est la population d'aujourd'hui des zones touchées ce jour-là, pas la population de 1985.

**Ce qu'il ne mesure pas :** le nombre de sinistrés. Dans un pixel de 27 km, tout le monde n'a pas été inondé. La bonne formulation est « habitants des zones où la pluie a été extrême », pas « personnes touchées par des inondations ».

**Ordres de grandeur (1 317 événements, 1981-2023) :**
- médiane : 2,2 millions d'habitants par événement ; quart des événements au-dessus de 5 millions ;
- maximum : 14,2 millions (28 septembre 2012, 390 pixels sur 450).
- Seules les localités du Sénégal comptent : les pixels situés en Gambie ou en Mauritanie n'ajoutent personne, ce qui règle pour cet indicateur la question des 42 % de pixels hors du pays.

**Contrôle :** pour les 1 317 événements, le nombre de pixels au-dessus de +2σ reconstruit à partir des anomalies quotidiennes est exactement celui du catalogue (`coverage_points`).

**Placement de la population (voir `resume.json`) :**

| Précision | Part de la population |
|---|---|
| Localité retrouvée par son nom exact | 72,7 % |
| Localité retrouvée par un nom approché (même commune) | 9,0 % |
| Centre de la commune (localité absente du fichier de coordonnées) | 18,2 % |

Les 553 communes du RGPH-5 ont toutes leur équivalent dans le fichier de l'ANSD : 477 par le nom, 61 par un nom approché dans le même département, 10 communes découpées depuis (Keur Massar Nord et Sud…), 5 par un alias vérifié. Toutes les correspondances sont dans `correspondance_communes_rgph5_ansd.csv` pour relecture.

**Fichiers :**
- `population_touchee_evenements.csv` : un événement par ligne ;
- `population_touchee_par_annee.csv` : par année, nombre d'événements et cumul « habitants × événements » (une même personne compte une fois par événement) ;
- `data/processed/localites_rgph5_placees.csv` : les 25 317 localités du RGPH-5 avec coordonnées, précision et pixel.

## 2. Communes reconstruites

**Pourquoi :** aucun contour public à jour des communes n'existe. GADM 4.1 en donne 431, dans un découpage ancien et sous une licence qui interdit la redistribution ; l'ANSD n'en publie pas.

Sources vérifiées avant de reconstruire (octobre 2026) :
- **ANSD** : interrogée par courriel, elle renvoie vers GADM et fournit les coordonnées des localités, sans contours ;
- **OCHA (COD-AB 2024)** : contours jusqu'aux arrondissements (125), pas de communes ;
- **GéoSénégal** (geosenegal.gouv.sn, données de l'ANAT) : la base au 1/200 000 décrit les limites administratives jusqu'à l'**arrondissement** (classe « région administrative de 3e ordre ») et date du découpage d'avant 2013 (elle mentionne les communautés rurales) ; la base au 1/50 000 ne compte que 62 feuilles, toutes dans la vallée du fleuve Sénégal (Dagana, Podor, Bakel, Matam, Saint-Louis...), sans la région de Dakar ;
- **GADM 4.1** : 431 communes, découpage ancien, redistribution interdite.

**Méthode :** chaque point du territoire est attribué à la localité ANSD la plus proche (diagramme de Voronoï), à l'intérieur de chacun des 46 départements OCHA 2024, puis les cellules sont regroupées par commune.

**Résultat :** 552 communes (le fichier ANSD en compte 553, mais « NGUEUNE SARR » et « NGUEuNE SARR », dans le département de Louga, sont la même commune écrite deux fois), emboîtées dans les 46 départements actuels, pour une superficie totale de 196 767 km² (Sénégal : environ 196 700 km²). Pour les 406 communes qui existent aussi dans GADM, le recouvrement médian (IoU) est de 0,78, et 96 % dépassent 0,5.

**Limites :**
- ce sont des **contours approximatifs** : la limite entre deux communes passe à mi-distance de leurs localités voisines, pas sur la limite officielle ;
- 32 communes ont des localités de part et d'autre d'une limite départementale ; elles sont rattachées au département où se trouve la plus grande partie de leur surface ;
- de petites enclaves peuvent apparaître quand une localité isolée est entourée par une autre commune.

**Licence :** dérivé des coordonnées de l'ANSD et des contours OCHA (CC BY-IGO), sans GADM.

**Fichiers :** `data/processed/communes_reconstruites_ansd.geojson` (1 Mo, simplifié à environ 200 m), `communes_reconstruites_controle.csv`, `communes_reconstruites_resume.json`.
