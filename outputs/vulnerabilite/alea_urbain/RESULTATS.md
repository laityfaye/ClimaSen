# Résultats : aléa d'inondation urbaine

*Calculé le 2 octobre 2026 par `scripts/32_alea_urbain.py`, selon `PROTOCOLE.md` (commit `8a6800d`, fixé avant tout calcul). Chiffres complets dans `resultats.json`.*

## En bref

**La piste est écartée.** La part du bâti en terrain bas ne distingue pas les départements touchés par les inondations documentées (T1 : AUC 0,47) et n'apporte rien au-delà de la population (T2 : p = 0,41). Conformément à la règle de décision du protocole, le résultat est publié tel quel et la mesure n'entre pas dans un indice.

## Tests du protocole

46 départements, dont 22 touchés au moins une fois (certitude A). AUC, bootstrap stratifié de 5 000 tirages et graine identiques au script 29.

| Test | Mesure | Résultat | Critère | Verdict |
|---|---|---|---|---|
| **T1** | AUC de U (part du bâti en terrain bas) | **0,468**, IC 95 % [0,307 ; 0,638] | borne basse > 0,5 | **non satisfait** |
| **T2** | Apport de U au-delà de la population (rapport de vraisemblance) | coefficient de rang(U) = 1,13 ; **p = 0,414** | p < 0,05 et coefficient positif | **non satisfait** |
| T3 | AUC de U_abs (bâti en terrain bas, km²) | 0,676 [0,498 ; 0,826] | rapporté | — |
| T4 | AUC de (rang(U) × E)^(1/2) | 0,693 [0,519 ; 0,848] | rapporté | — |
| Référence | AUC de la population 2023 seule | 0,845 [0,720 ; 0,945] | rapporté | — |

T3 et T4 dépassent 0,5 parce qu'ils contiennent la population : U_abs croît avec la taille des villes (ρ de Spearman avec la population = 0,54), et T4 inclut l'exposition. Aucun des deux ne fait mieux que la population seule.

## Sensibilité (pour information, sans effet sur la décision)

| Fenêtre | Seuil | AUC | IC 95 % |
|---|---|---|---|
| 11 × 11 (≈ 0,5 km) | −1 m | 0,564 | [0,400 ; 0,731] |
| 41 × 41 (≈ 2 km) | −1 m | 0,366 | [0,210 ; 0,534] |
| 21 × 21 | −0,5 m | 0,468 | [0,301 ; 0,638] |
| 21 × 21 | −2 m | 0,447 | [0,288 ; 0,625] |

Aucune variante n'a une borne basse au-dessus de 0,5.

## Pourquoi la mesure échoue

- **Elle repère les vallées, pas les cuvettes urbaines.** Le TPI compare une cellule à son voisinage d'un kilomètre. Il est le plus fort dans le relief du sud-est (moyenne de U : Kédougou 0,62, Kolda 0,44, Tambacounda 0,36).
- **Elle ne voit pas les plaines inondables.** Sur un terrain plat, aucune cellule n'est nettement plus basse que ses voisines : le delta de Saint-Louis (0,07) et le Saloum à Fatick (0,06) ont les valeurs les plus faibles.
- **Pikine, cité aux quatre dates, a la valeur la plus basse de la région de Dakar (0,19).** Ses inondations viennent de la remontée de la nappe dans les cuvettes des Niayes, sur des étendues plus larges que la fenêtre, et du drainage, comme le décrit le PDNA 2009. Le modèle Copernicus inclut en outre les toits, ce qui brouille la topographie des quartiers denses.

## Écarts d'exécution par rapport au protocole

Aucune définition, aucun seuil et aucun test n'ont été modifiés. Trois corrections techniques ont été nécessaires avant le premier résultat :
1. reprises automatiques des téléchargements après une coupure réseau ;
2. construction de la grille de 100 m avant la copie des tuiles GHSL : la première version lisait une fenêtre débordant de la tuile et décalait la grille (Dakar sans bâti, Ziguinchor sans cellule) ;
3. ajout de la tuile GHSL R7_C17, nécessaire pour l'extrême nord (Podor), au-delà de 16,3° N.
Un garde-fou arrête désormais le script si une zone n'a ni cellule ni bâti. Aucun résultat de test n'a été produit avant ces corrections.

## Ce que ça apprend

Un modèle de terrain mondial de 30 m ne suffit pas à décrire l'aléa d'inondation urbaine au Sénégal à l'échelle du département. Les pistes qui restent demandent des données locales :
- les emprises d'inondation observées (UNOSAT 2009 et 2012 pour Dakar, déjà dans `data/raw/inondations/sources/`) ;
- la profondeur de la nappe et l'état du drainage ;
- les données d'habitat du RGPH-5 demandées à l'ANSD.

Toute nouvelle mesure devra suivre la même démarche : protocole figé avant le calcul, test sur l'inventaire, publication du résultat quel qu'il soit.
