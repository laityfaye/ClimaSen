# L'indice de risque est-il robuste et cohérent avec les inondations réelles ?

*CLIMAT-SEN, module Vulnérabilité, 1er octobre 2026. Chiffres produits par `scripts/29_robustesse_indice.py` ; inventaire des inondations dans `data/raw/inondations/`.*

## En bref

- **Le haut du classement résiste au choix des poids.** Les classements restent proches de l'indice publié dans les variantes testées (ρ de Spearman de 0,67 à 0,94). Cinq départements sont dans le top 10 de toutes les variantes : Vélingara, Tambacounda, Kolda, Nioro du Rip et Goudomp.
- **L'indice ne retrouve pas les départements touchés par les inondations de 2005, 2009, 2012 et 2020.** L'AUC vaut 0,49 (IC 95 % [0,32 ; 0,67]), c'est-à-dire le niveau du hasard. Les départements touchés plusieurs fois sont même classés plus bas que les autres (AUC 0,31, IC [0,14 ; 0,49]).
- **C'est l'exposition qui explique les inondations documentées.** Seule, elle les distingue nettement (AUC 0,84, IC [0,70 ; 0,94]). L'aléa CHIRPS (0,37) et la vulnérabilité provisoire (0,31) vont dans le sens inverse.

## 1. Sensibilité aux pondérations

Les six variantes reposent sur les mêmes composantes A (aléa), E (exposition) et V (vulnérabilité), en rang centile :

| Variante | Formule |
|---|---|
| Géométrique (publiée) | (A·E·V)^1/3 |
| Moyenne simple | (A+E+V)/3 |
| Aléa ×2 | (A²·E·V)^1/4 |
| Exposition ×2 | (A·E²·V)^1/4 |
| Vulnérabilité ×2 | (A·E·V²)^1/4 |
| Sans vulnérabilité | (A·E)^1/2 |

| | 46 départements | 125 arrondissements |
|---|---|---|
| ρ de Spearman avec l'indice publié | 0,67 à 0,94 | 0,67 à 0,95 |
| ρ le plus bas entre deux variantes | 0,41 | 0,46 |
| Zones du top 10 communes aux 6 variantes | 5 (Vélingara, Tambacounda, Kolda, Nioro du Rip, Goudomp) | 4 (Bonconto, Saré Coly Sallé, Koussanar, Dioulacolon) |
| Zones entrant au moins une fois dans un top 10 | 22 | 17 |
| Écart de rang médian d'une zone entre variantes | 15 places | 33 places |

Le haut du classement (Kolda, Tambacounda, Nioro du Rip) est stable. Au-delà, les rangs dépendent fortement du poids donné à la vulnérabilité. Les variantes qui retirent la vulnérabilité ou doublent l'exposition s'écartent le plus. Dakar passe du 43e au 10e rang quand on retire la vulnérabilité, et au 35e rang quand on double l'exposition. Figure : `fig_sensibilite_departements.png`.

## 2. Inondations documentées

Les départements touchés ont été relevés dans des documents publics accessibles. Chaque ligne de l'inventaire cite le document, la page et un extrait. La certitude A désigne une zone nommée comme touchée par un document institutionnel ; la certitude B, une mention ambiguë ou un article de presse.

| Année | Source principale | Départements, certitude A | Certitude B |
|---|---|---|---|
| 2005 | PDNA 2009 (rapport de juin 2010) | Pikine, Guédiawaye | Dakar (Charte internationale) |
| 2009 | PDNA « Inondations urbaines à Dakar 2009 » (Gouvernement, Banque mondiale, ONU, CE) | Pikine, Guédiawaye, Keur Massar, Rufisque, Saint-Louis, Dagana, Podor, Matam, Kaolack, Kaffrine, Fatick, Mbour, Thiès, Kolda, Vélingara, Sédhiou, Tambacounda, Kédougou | Dakar, Foundiougne, Ziguinchor |
| 2012 | UNOSAT (11/09/2012), Charte internationale, OCHA via ReliefWeb | Pikine, Dakar, Mbacké (Touba), Kébémer (Darou Mousty), Fatick, Kaolack, Saint-Louis, Bambey | Guédiawaye (VOA), Keur Massar (« outer Pikine ») |
| 2020 | FICR, DREF MDRSN017 (14/09/2020) | Dakar, Pikine, Guédiawaye, Rufisque, Keur Massar, Thiès | |

**Choix de lecture.** Pour 2020, le DREF cite aussi 21 départements ayant reçu de **fortes pluies** (source ANACIM). Je ne les ai pas comptés comme inondés, faute de dégâts décrits. Pour 2012, l'étude de cas GFDRR (2014) ne cite que des **régions** (Matam, Kaffrine, Diourbel), sans département précis : ces mentions ne sont pas utilisées.

**Sources inaccessibles ou absentes.**
- EM-DAT : non consulté, l'accès demande un compte.
- DesInventar : le serveur a renvoyé une erreur ; aucune base Sénégal n'a pu être consultée.
- API ReliefWeb : elle exige un identifiant d'application approuvé.
- Rapports DREF 2012 de la FICR : refusés (HTTP 403).
- Atlas UNOSAT liés depuis la Charte : liens morts (404).
- 2005 : aucune source primaire trouvée ; les deux départements retenus viennent du PDNA de 2010.

Rien n'a été complété de mémoire.

## 3. Test

Les départements cités ont-ils un indice plus élevé ? Méthode :
- **AUC** : probabilité qu'un département touché ait un indice supérieur à un département non touché ; 0,5 correspond au hasard.
- **Intervalle de confiance à 95 %** : bootstrap stratifié, 5 000 tirages.
- **Test de Mann-Whitney** unilatéral.

| Groupe (certitude A) | Départements touchés | AUC | IC 95 % | p |
|---|---|---|---|---|
| 2005 | 2 | 0,15 | 0,02 – 0,28 | 0,95 |
| 2009 | 18 | 0,53 | 0,35 – 0,72 | 0,36 |
| 2012 | 8 | 0,35 | 0,17 – 0,55 | 0,90 |
| 2020 | 6 | 0,28 | 0,10 – 0,47 | 0,96 |
| Au moins une fois | 22 | 0,49 | 0,32 – 0,67 | 0,55 |
| Deux fois ou plus | 9 | 0,31 | 0,14 – 0,49 | 0,96 |

Ajouter les mentions de certitude B ne change pas la conclusion (au moins une fois : AUC 0,53).

AUC par composante, pour les départements touchés au moins une fois :

| Score | AUC |
|---|---|
| Exposition seule | **0,84** |
| Indice sans vulnérabilité | 0,69 |
| Indice publié | 0,49 |
| Ancien indice (30/09) | 0,45 |
| Aléa seul | 0,37 |
| Vulnérabilité seule | 0,31 |

Figure : `fig_validation_inondations.png`.

## 4. Interprétation

1. **Les inondations documentées sont surtout urbaines.** Elles touchent la banlieue de Dakar, Thiès, Kaolack, Saint-Louis et Fatick. Pikine est cité aux quatre dates. Ces zones ont une forte exposition, mais un **aléa CHIRPS faible** (0,17 à 0,38 pour les neuf départements touchés deux fois ou plus) et une vulnérabilité provisoire faible. Le haut du classement, au sud-est, est rural et presque absent des rapports.
2. **L'aléa mesure autre chose.** Il compte les jours de pluie extrême sur des mailles CHIRPS de 0,25° (environ 27 km). Les inondations de Dakar viennent de la saturation du drainage, de la remontée de la nappe et de l'occupation de zones basses, comme le dit le PDNA 2009. Ces causes n'apparaissent pas dans un cumul de pluie à cette échelle.
3. **La vulnérabilité provisoire joue contre la banlieue dakaroise.** La pauvreté est régionale, et la région de Dakar a le taux le plus bas (9,3 %, EHCVM).
4. **Biais de l'inventaire.** Les rapports humanitaires et satellitaires couvrent d'abord les villes et les zones où les dégâts sont visibles. Un département rural inondé peut ne pas avoir été cité. Le test mesure donc la cohérence avec les inondations *documentées*, pas avec toutes les inondations. Avec 46 départements, les intervalles de confiance restent larges.

## Conclusion pour le jury

Le classement est **stable en tête**, mais il **ne reproduit pas** la géographie des inondations documentées depuis 2005. Nous le présentons comme un indice de risque lié à la fréquence des pluies extrêmes, en zone surtout rurale, et non comme une carte des inondations urbaines. Les poids n'ont pas été ajustés pour améliorer ce résultat.

Les pistes, non réalisées à ce stade :
- un aléa d'inondation pluviale urbaine (zones basses, nappe, imperméabilisation) ;
- les données d'habitat du RGPH-5 pour la vulnérabilité.

Chaque variante devrait ensuite être évaluée contre cet inventaire.
