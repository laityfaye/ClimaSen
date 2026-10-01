# Faut-il moduler l'aléa avec le bulletin de veille ?

*CLIMAT-SEN, module Vulnérabilité, 1er octobre 2026. Chiffres produits par `scripts/31_modulation_saisonniere_alea.py`, à partir de `outputs/veille/` et `outputs/vulnerabilite/`.*

## Recommandation

**Ne pas multiplier l'aléa par le niveau du bulletin. Afficher le bulletin à côté de l'indice.** L'indice historique reste la seule valeur calculée. Le bulletin est présenté comme une information séparée, avec sa propre fiabilité.

## Pourquoi la modulation n'est pas défendable

1. **Elle ne change pas le classement.** Le bulletin donne un seul niveau pour tout le Sénégal, la probabilité qu'une saison soit « extrême ». Un facteur identique pour les 46 départements laisse l'ordre inchangé.

   | Facteur appliqué | Départements qui changent de rang | Variation de l'indice |
   |---|---|---|
   | ±10 % sur les indicateurs bruts, avant le rang centile | 0, pour tous les niveaux | 0 % |
   | ±10 % sur la composante A normalisée | 0 (bulletin faible) ; 4 (bulletin élevé ou très élevé) | −3,45 % / +3,23 % pour tous |

   Dans le second cas, les 4 changements (Kolda, Nioro du Rip, Kédougou, Goudiry) viennent seulement du plafond à 1. Kolda a déjà l'aléa maximal et ne peut pas monter. C'est un **artefact**, pas une information.

   La modulation ne ferait donc que déplacer tous les chiffres de 3 % environ, ce qui donnerait une fausse impression de précision.

2. **Aucune source saisonnière n'a de compétence démontrée.** L'AUC vaut 0,5 pour le hasard ; la fiabilité a été mesurée par un test de permutation, en prévision réelle.

   | Source | AUC | p | Fichier |
   |---|---|---|---|
   | Projection océanique novembre-avril | 0,533 | 0,395 | `competence_projection.json` |
   | Prévision C3S calibrée (ECMWF), qui fixe le niveau du bulletin | 0,594 | 0,192 | `calibration_c3s_ecmwf.json` |
   | C3S multi-modèle (variantes V2 à V4) | 0,484 à 0,492 | ≥ 0,52 | `evaluation_c3s_variantes.json` |

   Les états océaniques saisonniers (El Niño, La Niña, neutre, transition) n'ont pas non plus de lien avec l'intensité des extrêmes. Le test de Kruskal-Wallis donne p de 0,23 à 0,90 (`outputs/clustering_saisonnier/resultats.json`).

3. **Le bilan des bulletins rétrospectifs (1998-2023) est proche du hasard.**

   | Niveau du bulletin | Saisons | Dont saisons extrêmes |
   |---|---|---|
   | Faible | 3 | 1 (33 %) |
   | Normal | 14 | 7 (50 %) |
   | Élevé | 9 | 5 (56 %) |

   Sur l'ensemble des saisons vérifiées, la part d'années extrêmes est de 50 %. En **2009**, année d'inondations majeures, le bulletin était « faible » : la modulation aurait **réduit** l'aléa cette année-là.

4. **Elle contredirait la règle du module de veille.** Le bulletin lui-même n'affiche pas de niveau tant que la compétence n'est pas démontrée (`veille/bulletin.py`, `presentation()`). Il montre seulement une probabilité indicative face à la référence d'une saison sur trois. Utiliser ce niveau comme multiplicateur reviendrait à lui donner un poids que la veille lui refuse.

5. **Le bulletin en cours ne donne pas de niveau.** Pour la saison 2027, il est « indéterminé » : la prévision C3S paraît en avril.

Une modulation **différenciée par zone** serait possible en théorie, par exemple en projetant la configuration océanique prévue sur sa carte de pluie au Sénégal. Mais elle repose sur la projection (AUC 0,53) et sur des configurations qui ne prédisent pas l'intensité des extrêmes. Elle n'est pas défendable non plus.

## Présentation proposée

Sur la page Vulnérabilité, un encadré « Saison à venir » placé à côté de l'indice, sans aucun calcul commun :

- il lit le bulletin le plus récent avec la même règle d'affichage que la page Veille ;
- il montre la probabilité indicative et la référence de 33 % quand la compétence n'est pas démontrée, un niveau uniquement si elle l'est, et « pas encore de prévision » si le bulletin est indéterminé ;
- il renvoie vers la page Veille pour le détail : carnet de fiabilité, analogues.

### Texte d'avertissement à afficher

> **Saison à venir : information indicative, non significative statistiquement.**
> Le bulletin de veille estime la probabilité que la prochaine saison des pluies soit « extrême » pour l'ensemble du Sénégal. Sa capacité à prévoir n'est pas démontrée : sur 1998-2023, la prévision C3S fait à peine mieux que le hasard (AUC 0,59, p = 0,19), et la projection océanique ne fait pas mieux en conditions réelles (AUC 0,53).
> Ce bulletin **ne modifie pas** l'indice de risque, qui repose sur la fréquence historique des pluies extrêmes (CHIRPS 1981-2023), la population (ANSD RGPH-5) et la pauvreté (ANSD EHCVM). Il ne remplace pas les alertes de l'ANACIM.

Version courte, pour une bulle d'aide ou Jarvis :

> Indicatif, non significatif statistiquement : le bulletin de saison ne modifie pas l'indice de risque.

## Si la modulation est tout de même conservée

À réserver à une démonstration, jamais à l'indice publié :
- un paramètre désactivé par défaut ;
- un facteur appliqué avant la normalisation, la seule variante sans artefact, mais alors sans aucun effet visible ;
- l'avertissement ci-dessus affiché à côté ;
- un indice de référence toujours affiché en premier.

**Condition pour réactiver la question** : qu'une source saisonnière atteigne une compétence démontrée, avec une AUC significative en prévision réelle. Le carnet de fiabilité de la page Veille permet de le suivre.
