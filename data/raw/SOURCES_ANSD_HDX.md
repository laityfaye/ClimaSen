# Sources des données ANSD et HDX

Téléchargées le 30 septembre 2026 pour le Hackathon ANSD 2026 (module Vulnérabilité).
Toute donnée affichée sur la plateforme doit citer la source indiquée ici.

## ansd/

| Fichier | Source | Contenu | Échelle |
|---|---|---|---|
| `rgph_repertoire_localites_1988-2023.csv` | ANSD, Répertoire des localités — https://www.ansd.sn/donnees-recensements (export CSV : `https://www.ansd.sn/data-recensement.csv?page&_format=csv`) | Concessions, ménages, hommes, femmes, population par localité pour les recensements 1988, 2002, 2013 et 2023 (RGPH-5 : 25 317 localités, 548 communes, 46 départements, 18 152 795 habitants). Encodage UTF-8 avec BOM. Pas de coordonnées. | Région, département, commune (arrondissement ou ville), localité |
| `ehcvm_2021-2022_pauvrete_par_region.csv` | ANSD, *Enquête harmonisée sur les conditions de vie des ménages (EHCVM II) 2021-2022, Rapport final*, Tableau III-2 « Indicateurs de la pauvreté selon la région », p. 34 | Part de la population, consommation moyenne par tête (FCFA/an), taux de pauvreté P0, profondeur P1, sévérité P2, contribution C0, indice de Gini. Transcrit à la main depuis le PDF (les parts et les contributions totalisent 100 %). | Région (14) |
| `Rapport_Final_EHCVM_2021-2022_VF.pdf` | https://www.ansd.sn/sites/default/files/2024-07/Rapport_Final_EHCVM_2021-2022_VF.pdf | Rapport complet (122 pages) | National, milieu, région |
| `Atlas-demographique_RGPH5.pdf` | https://www.ansd.sn/sites/default/files/2024-12/Atlas-demographique_RGPH5.pdf | Atlas démographique du RGPH-5 (cartes et analyses) | Région, département |

### Transcriptions complémentaires (1er octobre 2026)

Chaque transcription est vérifiée par `py -3 scripts/30_controle_transcriptions_ansd.py`, qui écrit `ansd/controle_transcriptions.txt`.

**Rapport EHCVM 2021-2022.** Les pages du PDF coïncident avec la pagination imprimée.

| Fichier | Source exacte | Échelle | Mode de transcription | Contrôle |
|---|---|---|---|---|
| `ehcvm_2021-2022_assainissement_par_region.csv` | Tableau VII-11 « Indicateurs d'accès à l'assainissement selon la région », p. 83 | Région (14), % des ménages, 2021-2022 | Texte extrait ; les colonnes « Toilettes publiques » et « Autre » étaient décalées et ont été réattribuées, puis vérifiées sur l'image de la page | Chaque ligne totalise 99,9 à 100,1 % |
| `ehcvm_2021-2022_services_chocs_par_region.csv` | Eau potable : carte VII-2, p. 81. Électricité : carte VII-1, p. 79. Insécurité alimentaire FIES : figure VIII-3, p. 93. Ménages ayant subi un choc dans les 3 dernières années : figure VIII-6, p. 95 | Région (14), 2021-2022 | Étiquettes lues sur les pages rendues en image | Voir les deux mises en garde ci-dessous ; FIES et chocs retombent sur le national à ±2 points |
| `ehcvm_2021-2022_chocs_par_milieu.csv` | Tableau VIII-2 « Principaux chocs subis selon le milieu de résidence », p. 96 | Dakar / autres urbains / rural / national, % des ménages ayant connu un choc | Texte extrait | Les valeurs nationales sont comprises entre celles des milieux |

Mises en garde sur `ehcvm_2021-2022_services_chocs_par_region.csv` :
- **Eau potable** : la moyenne régionale pondérée vaut 81,7 %, contre 93,7 % au national (p. 80). La carte suit une autre définition, ou contient une erreur. À clarifier avec l'ANSD avant usage.
- **Électricité à Ziguinchor** : la carte indique 89,91, le texte 89,3. La valeur de la carte est retenue.

Le rapport EHCVM ne donne **pas** la pauvreté selon le milieu à l'intérieur de chaque région. Le Tableau II-1 ne croise que Dakar urbain, les autres urbains et le rural, au niveau national.

Pour les inondations, le texte p. 96 dit 7,2 % de ménages touchés, alors que le Tableau VIII-2 donne 8,2 % au national. Le fichier reprend le tableau.

**Atlas démographique RGPH-5 (2023).** Les pages du PDF sont des doubles pages : la page 3 du PDF correspond aux pages imprimées 4-5.

| Fichier | Source exacte | Échelle | Mode de transcription | Contrôle |
|---|---|---|---|---|
| `atlas_rgph5_2023_classes_extremes_departements.csv` | Atlas démographique RGPH-5, 9 cartes : I-2 densité, I-5 part des 0-5 ans, I-10 taux d'urbanisation, I-12 rapport de dépendance, VIII-4 éclairage électrique, VIII-7 eau de boisson améliorée, VIII-10 ménages propriétaires, IX-1 femmes cheffes de ménage, XI-1 prévalence du handicap | Département, 2023 | Commentaire de chaque carte, lu sur les pages rendues en image car leur texte n'est pas extractible. Une ligne par département cité avec le seuil de classe ; les mentions « région de X » sont développées en départements (colonne `mention`) | Tous les départements cités existent parmi les 46. Les classes de densité concordent exactement avec la densité calculée par le script 26 |

L'Atlas ne donne **pas** de valeur par département. Ses cartes sont des images en 5 classes de quantiles, sans étiquette chiffrée. Seuls la valeur nationale et les départements des deux classes extrêmes sont écrits. L'Atlas indique aussi 58 688 hab/km² pour Guédiawaye, contre 26 526 dans notre calcul : la superficie utilisée diffère de celle d'OCHA (14,05 km²).

Microdonnées EHCVM : catalogue ANADS, https://anads.ansd.sn (accès sur demande).

## hdx/

| Fichier | Source | Contenu |
|---|---|---|
| `sen_admin_boundaries.xlsx`, `sen_admin0` à `sen_admin3` (`.geojson`) | OCHA, *Senegal — Subnational Administrative Boundaries* (COD-AB), https://data.humdata.org/dataset/cod-ab-sen — licence **CC BY-IGO** ; source : Gouvernement du Sénégal, mis à jour par OCHA/ROWCA ; version v02, valide au 20/05/2024 | Limites nationales (admin0), régions (14), départements (46, dont Keur Massar), arrondissements (125), avec codes P-code. Pas de contours de communes (admin4 seulement en points). Les fichiers `_em` sont une variante de la même géométrie. |

Attention : `sen_adminpoints.geojson` ne contient pas de points admin4. Ses 186 points sont les points d'étiquette des niveaux 0 à 3 (1 pays + 14 régions + 46 départements + 125 arrondissements). `sen_admincapitals.geojson` donne 55 chefs-lieux avec coordonnées (niveaux 0 à 3). L'arrondissement SN010404 (Rufisque) s'appelle « N/A » dans HDX ; il contient les communes de Bargny et Sendou.

## osm/

| Fichier | Source | Contenu |
|---|---|---|
| `communes_urbaines_osm.csv` | © OpenStreetMap contributors, **ODbL 1.0**, via Nominatim (https://nominatim.openstreetmap.org), interrogé le 30/09/2026 par `py -3 scripts/27_indice_risque_arrondissements.py --osm` | Un point par commune urbaine hors arrondissement (56 communes) : requête, type OSM (seulement ville, bourg ou village), identifiant OSM, résultats écartés et distance au contour HDX. Il sert à placer les 15 communes qui ne sont ni dans GADM ni chefs-lieux HDX (Richard-Toll, Joal-Fadiouth, Bargny, Dahra, Kahone…). Pour les 39 chefs-lieux présents dans les deux sources, le point OSM et le point `sen_admincapitals` tombent dans le même arrondissement. |

## Correspondance communes → arrondissements (script 27)

Les tables sont dans `data/processed/correspondance_communes_arrondissements.csv` (2023) et `correspondance_2013_arrondissements.csv`. Elles utilisent aussi les communes GADM 4.1 niveau 4 (`data/geographic/senegal_boundaries/gadm41_SEN_4.shp`), qui couvrent les communes des « villes » de Dakar, Pikine, Guédiawaye, Rufisque et Thiès, mais pas les autres communes urbaines. La commune « Pikine Nord » du RGPH-5 correspond à « Pikine Sud » du RGPH 2013 et de GADM : les 18 quartiers sont identiques.

## Correspondances connues

Les noms de départements du RGPH-5 correspondent aux 46 départements HDX après ces alias :

| RGPH-5 | HDX (`adm2_name`) |
|---|---|
| KOUPENTOUM | Koumpentoum |
| MALEM HODDAR | Malem Hodar |
| MEDINA YORO FOULAH | Medina Yoro Foula |
| NIORO | Nioro du Rip |
| RANEROU FERLO | Ranerou |

Périmètres 2013 → 2023 : le département de Keur Massar (créé en 2021) n'existe pas dans le recensement 2013. Pour comparer 2013 et 2023 à périmètre constant, le script 26 le reconstitue avec ses communes de 2013 : Keur Massar, Malika, Yeumbeul Nord et Yeumbeul Sud (alors dans Pikine), et Jaxaay-Parcelles-Niakoul Rap (alors dans Rufisque). Le total national 2013 reste de 13 508 715 habitants. Si l'on compare localité par localité, on ne trouve aucun autre transfert entre départements, seulement des homonymes isolés (quelques centaines d'habitants).

Communes : 548 dans le RGPH-5 2023, mais seules 359 correspondent par le nom aux 428 communes de GADM 4.1 (`data/geographic/`). Les contours officiels des communes restent à obtenir auprès de l'ANSD.

## inondations/ (validation historique, script 29)

`zones_touchees_2005_2009_2012_2020.csv` recense les départements touchés par ces quatre inondations. Il a été relevé à la main le 1er octobre 2026, uniquement à partir des documents archivés dans `inondations/sources/` : PDNA 2009 (Banque mondiale, juin 2010), DREF FICR MDRSN017 (2020), rapport UNOSAT Dakar du 31/08/2012, pages de la Charte internationale (2005, 2009, 2012), fiche ReliefWeb FL-2012-000169-SEN, article VOA du 11/09/2012 et étude de cas GFDRR 2014.
- **Contenu de chaque ligne** : document, page du PDF et extrait cité.
- **Certitude A** : zone nommée comme touchée par un document institutionnel.
- **Certitude B** : mention ambiguë ou article de presse.
- **Sources non consultées ou inaccessibles** : EM-DAT (accès sur compte), DesInventar (erreur serveur), API ReliefWeb (identifiant d'application exigé), DREF FICR de 2012 (HTTP 403), atlas UNOSAT de 2012 (liens morts).

## Contours allégés (page Vulnérabilité)

`data/processed/contours_admin2_simplifies.geojson` (0,23 Mo) et `contours_admin3_simplifies.geojson` (0,35 Mo) sont dérivés de `sen_admin2` et `sen_admin3` par `py -3 scripts/28_contours_simplifies.py`. La méthode est `shapely.coverage_simplify` avec une tolérance de 0,002° (~220 m) : chaque frontière commune n'est simplifiée qu'une fois, ce qui évite trous et chevauchements entre zones voisines. Les coordonnées sont arrondies à 1e-4°. L'écart de surface est de 0,02 % en médiane et de 1,04 % au plus (Dakar Plateau). Ces fichiers restent sous licence OCHA CC BY-IGO. Seule la page les lit : les originaux ne sont jamais chargés à l'affichage.

## Taille

Les GeoJSON HDX pèsent environ 75 Mo au total. Avant de les versionner dans Git, garder seulement ce qui sert (probablement `sen_admin2.geojson`) ou les exclure dans `.gitignore`.
