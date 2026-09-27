"""Qu'est-ce qu'une annee extreme ?

Mesure: l'EMPREINTE de la saison, somme des coverage_percent de tous ses
evenements extremes (CHIRPS > 2 sigma). Elle combine le nombre d'evenements
et leur etendue: une saison avec beaucoup d'evenements etendus inonde plus
de territoire. Verifie sur 1981-2023: les 8 annees d'inondations majeures
documentees sont toutes dans les 10 premieres.

Une annee est extreme si son empreinte depasse le tiers superieur (quantile
2/3) des annees de reference. Le seuil est calcule sur la periode fournie:
en validation, sur les seules annees d'apprentissage.

L'intensite maximale (max_precip) n'est PAS retenue: son top 10 ne contient
que 2 des 8 annees d'inondations (1985 et 1981 y figurent).
"""
import numpy as np
import pandas as pd

from . import EVENEMENTS, INONDATIONS_CONNUES

QUANTILE = 2 / 3


def empreinte(evenements=None, debut=1981, fin=None):
    """Serie annuelle de l'empreinte (annees sans evenement = 0)."""
    if evenements is None:
        evenements = pd.read_csv(EVENEMENTS, usecols=["year", "coverage_percent"])
    fin = int(evenements["year"].max()) if fin is None else fin
    serie = (evenements.groupby("year")["coverage_percent"].sum()
             .reindex(range(debut, fin + 1), fill_value=0.0).astype(float))
    serie.name = "empreinte"
    return serie


def seuil(serie, annees=None):
    valeurs = serie if annees is None else serie.loc[list(annees)]
    return float(np.quantile(valeurs.values, QUANTILE))


def classement(serie=None):
    """Tableau annee par annee: empreinte, rang, extreme ou non, inondation."""
    serie = empreinte() if serie is None else serie
    s = seuil(serie)
    table = pd.DataFrame({
        "empreinte": serie.round(1),
        "rang": serie.rank(ascending=False, method="min").astype(int),
        "extreme": serie > s,
        "inondation_documentee": serie.index.isin(INONDATIONS_CONNUES),
    })
    table.index.name = "annee"
    return table, s


def verification_definition(serie=None):
    """Combien d'inondations documentees la definition retrouve-t-elle ?"""
    table, s = classement(serie)
    connues = table[table["inondation_documentee"]]
    return {
        "seuil": round(s, 1),
        "inondations_documentees": len(connues),
        "classees_extremes": int(connues["extreme"].sum()),
        "rangs": {int(a): int(r) for a, r in connues["rang"].items()},
        "annees_de_reference": len(table),
    }
