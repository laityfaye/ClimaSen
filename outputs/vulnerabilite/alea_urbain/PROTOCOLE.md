# Protocole : aléa d'inondation urbaine

**Protocole fixé le 2 octobre 2026, avant tout téléchargement de données et avant tout calcul.**
Ce fichier est commité avant le script qui l'applique : son horodatage Git en fait foi. Toute modification ultérieure de ce protocole doit être faite dans un commit séparé, expliquée et datée, et les résultats de la version d'origine restent publiés.

Auteur : Thierno DIEDHIOU. Branche : `thierno/alea-urbain`, partie de `phase2-0` au commit `e9cf1d6`.

## 1. Question

L'indice de risque actuel ne retrouve pas les départements touchés par les inondations documentées de 2005, 2009, 2012 et 2020 (AUC 0,49, `outputs/vulnerabilite/robustesse/note_robustesse.md`). Ces inondations sont surtout urbaines, et l'aléa CHIRPS (jours de pluie extrême sur des mailles d'environ 27 km) ne les voit pas.

**Question :** une mesure du bâti situé en terrain bas distingue-t-elle les départements touchés mieux que le hasard, **et apporte-t-elle une information que la population seule n'apporte pas** ?

La seconde partie de la question est essentielle : les rapports d'inondation couvrent d'abord les zones peuplées, donc la population « prédit » mécaniquement les zones documentées (AUC 0,84). Un nouvel aléa n'est utile que s'il fait mieux que cette évidence.

## 2. Données

| Donnée | Source | Version | Licence |
|---|---|---|---|
| Altitude | Copernicus DEM GLO-30, tuiles de 1° couvrant le Sénégal (bucket public `copernicus-dem-30m` sur AWS) | Diffusion 2021 | Licence Copernicus DEM (usage libre avec attribution) |
| Surface bâtie | GHSL, GHS-BUILT-S, époque 2020, résolution 100 m, projection Mollweide (JRC, Commission européenne) | R2023A | CC BY 4.0 |
| Contours | OCHA COD-AB Sénégal, départements et arrondissements | v02 (2024) | CC BY-IGO |
| Inondations documentées | `data/raw/inondations/zones_touchees_2005_2009_2012_2020.csv` | Version du commit `e9cf1d6`, figée | Sources citées ligne par ligne |

Aucune autre donnée ne sera ajoutée pour améliorer le résultat.

## 3. Définitions (figées)

1. **Grille de travail :** la grille GHSL de 100 m. L'altitude Copernicus est ramenée sur cette grille par moyenne.
2. **Terrain bas :** une cellule est en terrain bas si son altitude est inférieure d'au moins **1 m** à l'altitude moyenne d'une fenêtre carrée de **21 × 21 cellules** centrée sur elle (environ 1 km de côté). C'est un indice de position topographique (TPI) ≤ −1 m.
3. **Bâti :** la surface bâtie GHSL de la cellule, en m² (de 0 à 10 000).
4. **Mesure principale, U :** pour chaque département, **la part de sa surface bâtie située en terrain bas** = surface bâtie en terrain bas / surface bâtie totale.
5. **Mesure secondaire, U_abs :** la surface bâtie en terrain bas, en km².
6. Une cellule appartient à un département si son centre est dans le contour OCHA.

## 4. Tests (figés)

Échantillon : les 46 départements. Cas positifs : les départements de certitude A touchés **au moins une fois** (22 départements), comme dans le script 29. Même procédure de bootstrap stratifié (5 000 tirages).

| Test | Ce qu'il mesure | Critère |
|---|---|---|
| **T1 (principal)** | AUC de U | U « distingue les départements touchés » si la **borne basse de l'IC 95 % est au-dessus de 0,5** |
| **T2 (principal)** | Apport de U au-delà de la population : régression logistique `touché ~ rang(population 2023) + rang(U)`, test du rapport de vraisemblance sur U | U « apporte une information propre » si **p < 0,05** et si le coefficient de U est positif |
| T3 (secondaire) | AUC de U_abs | Rapporté, sans critère de décision |
| T4 (secondaire) | AUC du score urbain (U × E)^(1/2), E = exposition du script 26 | Rapporté, sans critère de décision |

## 5. Règle de décision (figée)

- **Si T1 et T2 sont satisfaits :** U entre sur la plateforme comme « aléa d'inondation urbaine », dans un **second indice** (risque d'inondation urbaine), à côté de l'indice actuel, qui devient le « risque pluviométrique ».
- **Si seul T1 est satisfait :** U est publié comme indicateur descriptif (« part du bâti en terrain bas »), sans indice de risque, en précisant qu'il n'apporte rien de plus que la population.
- **Si T1 n'est pas satisfait :** le résultat est publié tel quel, comme une piste testée et écartée.

Dans tous les cas, les résultats des quatre tests sont publiés dans `outputs/vulnerabilite/alea_urbain/`.

## 6. Analyses de sensibilité (pour information, jamais pour choisir)

Les variantes suivantes seront calculées et publiées, mais **ne servent pas à choisir la définition** :
- fenêtre de 11 × 11 et de 41 × 41 cellules (environ 0,5 et 2 km) ;
- seuils de −0,5 m et de −2 m ;
- indice calculé à l'échelle des 125 arrondissements (description seulement : l'inventaire est départemental).

## 7. Limites connues avant le calcul

- **Copernicus DEM est un modèle de surface** : il inclut les toits et les arbres. Dans les quartiers denses, les rues peuvent apparaître « basses » par rapport aux bâtiments. Les modèles de terrain nu (FABDEM) sont sous licence non commerciale et n'ont pas été retenus.
- La précision verticale annoncée de Copernicus DEM (moins de 4 m en absolu) est du même ordre que le seuil de 1 m ; le TPI compare des cellules voisines, ce qui limite mais n'élimine pas cette erreur.
- Le terrain bas ne décrit ni la nappe phréatique ni l'état du drainage, citées par le PDNA 2009 comme causes des inondations de la banlieue de Dakar.
- Avec 46 départements et 22 cas positifs, les intervalles de confiance resteront larges.
- L'inventaire est biaisé vers les zones urbaines et documentées (voir la note de robustesse).

## 8. Dépendances

La lecture des fichiers GeoTIFF demande `rasterio`, absent de `requirements.txt` à la date du protocole. Son ajout sera proposé dans un commit séparé.
