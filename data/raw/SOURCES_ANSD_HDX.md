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

Microdonnées EHCVM : catalogue ANADS, https://anads.ansd.sn (accès sur demande).

## hdx/

| Fichier | Source | Contenu |
|---|---|---|
| `sen_admin_boundaries.xlsx`, `sen_admin0` à `sen_admin3` (`.geojson`) | OCHA, *Senegal — Subnational Administrative Boundaries* (COD-AB), https://data.humdata.org/dataset/cod-ab-sen — licence **CC BY-IGO** ; source : Gouvernement du Sénégal, mis à jour par OCHA/ROWCA ; version v02, valide au 20/05/2024 | Limites nationales (admin0), régions (14), départements (46, dont Keur Massar), arrondissements (125), avec codes P-code. Pas de contours de communes (admin4 seulement en points). Les fichiers `_em` sont une variante de la même géométrie. |

## Correspondances connues

Les noms de départements du RGPH-5 correspondent aux 46 départements HDX après ces alias :

| RGPH-5 | HDX (`adm2_name`) |
|---|---|
| KOUPENTOUM | Koumpentoum |
| MALEM HODDAR | Malem Hodar |
| MEDINA YORO FOULAH | Medina Yoro Foula |
| NIORO | Nioro du Rip |
| RANEROU FERLO | Ranerou |

Communes : 548 dans le RGPH-5 2023, mais seules 359 correspondent par le nom aux 428 communes de GADM 4.1 (`data/geographic/`). Les contours officiels des communes restent à obtenir auprès de l'ANSD.

## Taille

Les GeoJSON HDX pèsent environ 75 Mo au total. Avant de les versionner dans Git, garder seulement ce qui sert (probablement `sen_admin2.geojson`) ou les exclure dans `.gitignore`.
