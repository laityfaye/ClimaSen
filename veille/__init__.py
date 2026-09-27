"""Veille pre-saison ClimatSen: bulletin annuel de niveau de risque.

Chaque annee en avril, avant la saison des pluies, le bulletin repond a:
"la saison qui vient sera-t-elle une annee extreme, comme 1999, 2005, 2010,
2012, 2020 ou 2022 ?" Il combine deux sources, aux roles distincts:

  - la prevision saisonniere officielle Copernicus C3S (modeles dynamiques),
    traduite en probabilite d'annee extreme par calibration sur CHIRPS:
    c'est elle qui FIXE le niveau de risque (veille.c3s);
  - la projection de l'etat oceanique observe de novembre a avril sur les
    configurations de reference du memoire (K-Means des evenements): elle
    EXPLIQUE le bulletin et donne une indication experimentale, dont la
    competence mesuree est toujours affichee (veille.projection).

Pourquoi ce partage: valide sans fuite d'information (voir
veille.projection.evaluer), la projection a une competence significative
quand l'annee testee est seulement exclue (AUC ~0,7), mais nulle en
conditions reelles de prevision (apprentissage sur le passe seul). Elle ne
peut donc pas decider seule d'une alerte.

Le calcul lourd tourne hors ligne (scripts/19 et 20); le dashboard et Jarvis
ne lisent que les bulletins JSON de outputs/veille/.
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_SORTIE = RACINE / "outputs" / "veille"
CUBE_SST = RACINE / "data" / "processed" / "sst_cube_1deg.npz"
EVENEMENTS = RACINE / "data" / "processed" / "extreme_events_phases_senegal.csv"
CLUSTERING = RACINE / "outputs" / "clustering"

# Mois de l'etat oceanique: novembre (n-1) a avril (n), (decalage d'annee, mois).
MOIS_ETAT = ((-1, 11), (-1, 12), (0, 1), (0, 2), (0, 3), (0, 4))

# Annees d'inondations majeures documentees au Senegal: servent a VERIFIER la
# definition d'une annee extreme, jamais a l'apprentissage.
INONDATIONS_CONNUES = (1999, 2003, 2005, 2009, 2010, 2012, 2020, 2022)
