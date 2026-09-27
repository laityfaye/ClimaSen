# -*- coding: utf-8 -*-
"""Etats oceaniques saisonniers et hierarchie avec les clusters du script 11.

Deux niveaux (decision du 27/09/2026):
  - NIVEAU 1, les ETATS: 4 configurations saisonnieres robustes, obtenues par
    scripts/24_clustering_saisonnier.py (composites par annee x phase,
    significatives face au hasard, stables). Ce sont les etats du Pacifique
    tropical: El Nino, La Nina, neutre, transition apres un fort El Nino.
  - NIVEAU 2, les CONFIGURATIONS: les clusters d'evenements du script 11
    (typologie descriptive), chacun rattache a l'etat dans lequel tombent la
    plupart de ses evenements.

Le fichier des etats est ecrit une fois (construire). La hierarchie, elle, est
recalculee a la lecture a partir des sorties du script 11: relancer le
clustering avec un autre k depuis le dashboard la garde juste.

Nommage des etats, par une regle fixe sur les indices (pas a la main):
  - le Nino 3.4 moyen le plus eleve: "El Nino";
  - le suivant: "Neutre";
  - des deux restants, celui dont l'ocean Indien (IOBM) est le plus chaud:
    "Transition apres El Nino" (le bassin indien reste chaud l'annee qui suit
    un fort El Nino), l'autre: "La Nina".

Usage: py -3 -m veille.etats   (reconstruit le fichier depuis les sorties du script 24)
"""
import json

import numpy as np
import pandas as pd

from . import EVENEMENTS, RACINE

RESULTATS_24 = RACINE / "outputs" / "clustering_saisonnier" / "resultats.json"
FICHIER = RACINE / "outputs" / "clustering_saisonnier" / "etats_saisonniers.json"
CLUSTERING = RACINE / "outputs" / "clustering"
INDICES = RACINE / "data" / "raw" / "climate_indices" / "daily_indices_all.csv"
PHASES = ("Phase_1_debut", "Phase_2_pleine", "Phase_3_fin")
SEUIL_RATTACHEMENT = 0.6

DESCRIPTIONS = {
    "El Niño": "Pacifique équatorial est et central nettement plus chaud que la normale",
    "La Niña": "Pacifique équatorial froid, Atlantique tropical nord légèrement chaud",
    "Neutre": "Pacifique proche de la normale, légèrement chaud au centre",
    "Transition après El Niño": "Pacifique est qui se refroidit, océan Indien et Pacifique ouest chauds",
}
COULEURS = {"El Niño": "#EF4444", "La Niña": "#2563EB", "Neutre": "#94A3B8",
            "Transition après El Niño": "#F59E0B"}


class EtatsIndisponibles(Exception):
    pass


# =============================================================================
# Construction (une fois, apres le script 24)
# =============================================================================
def _saisons(resultats):
    bloc = resultats["resultats"]["Toutes_phases"]["methodes"]["kmeans"]
    if not bloc.get("saisons_par_cluster"):
        raise EtatsIndisponibles("Le script 24 n'a retenu aucun etat pour 'Toutes phases'.")
    code = {"P%d" % (i + 1): p for i, p in enumerate(PHASES)}
    saisons = {}
    for c, liste in bloc["saisons_par_cluster"].items():
        for s in liste:
            annee, p = s.split("-")
            saisons[(int(annee), code[p])] = int(c)
    return saisons


def construire(resultats=None):
    """Nomme les etats du script 24 et ecrit etats_saisonniers.json."""
    if resultats is None:
        if not RESULTATS_24.is_file():
            raise EtatsIndisponibles("Sorties du script 24 absentes: py -3 scripts/24_clustering_saisonnier.py")
        resultats = json.loads(RESULTATS_24.read_text(encoding="utf-8"))
    saisons = _saisons(resultats)
    ev = pd.read_csv(EVENEMENTS, usecols=["date", "year", "phase"], parse_dates=["date"])
    ind = pd.read_csv(INDICES, parse_dates=["date"]).set_index("date")
    profil = {}
    for c in sorted(set(saisons.values())):
        jours = ev[[saisons.get((y, p)) == c for y, p in zip(ev["year"], ev["phase"])]]["date"]
        moy = ind.loc[ind.index.isin(jours)].mean()
        profil[c] = {k: round(float(moy[k]), 2) for k in ("Nino34", "TNA", "TSA", "IOBM", "AMO")}
    ordre = sorted(profil, key=lambda c: -profil[c]["Nino34"])
    noms = {ordre[0]: "El Niño", ordre[1]: "Neutre"}
    restants = sorted(ordre[2:], key=lambda c: -profil[c]["IOBM"])
    if restants:
        noms[restants[0]] = "Transition après El Niño"
    for c in restants[1:]:
        noms[c] = "La Niña"
    etats = []
    for c in ordre:
        nom = noms[c]
        membres = sorted(s for s, e in saisons.items() if e == c)
        etats.append({"id": int(c), "nom": nom, "description": DESCRIPTIONS.get(nom, ""),
                      "couleur": COULEURS.get(nom, "#94A3B8"),
                      "indices_moyens": profil[c], "n_saisons": len(membres),
                      "annees": sorted({a for a, _ in membres})})
    sortie = {"source": "scripts/24_clustering_saisonnier.py (K-Means, Toutes phases, k=4)",
              "regle_de_nommage": __doc__.split("Nommage des etats")[1].split("Usage")[0].strip(),
              "etats": etats,
              "saisons": [{"annee": a, "phase": p, "etat": e} for (a, p), e in sorted(saisons.items())]}
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    return sortie


# =============================================================================
# Lecture
# =============================================================================
def charger():
    if not FICHIER.is_file():
        raise EtatsIndisponibles("Etats saisonniers absents: py -3 -m veille.etats")
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def etat_de_saison(annee, phase, donnees=None):
    donnees = donnees or charger()
    for s in donnees["saisons"]:
        if s["annee"] == int(annee) and s["phase"] == phase:
            return next(e for e in donnees["etats"] if e["id"] == s["etat"])
    return None


def hierarchie(phase="All_phases", donnees=None, evenements=None):
    """Rattachement de chaque cluster du script 11 (phase donnee) a un etat.

    evenements: DataFrame 'events_with_clusters' deja charge (sinon lu).
    Retourne {"etats": [...], "clusters": {k: {...}}, "cramer_v": float,
              "tableau": {cluster: {etat_nom: n}}}.
    """
    donnees = donnees or charger()
    if evenements is None:
        chemin = CLUSTERING / phase / ("%s_events_with_clusters.csv" % phase)
        if not chemin.is_file():
            raise EtatsIndisponibles("Clusters du script 11 absents pour %s." % phase)
        evenements = pd.read_csv(chemin, usecols=["cluster", "year", "phase"])
    par_saison = {(s["annee"], s["phase"]): s["etat"] for s in donnees["saisons"]}
    noms = {e["id"]: e["nom"] for e in donnees["etats"]}
    ev = evenements.assign(etat=[par_saison.get((int(y), p))
                                 for y, p in zip(evenements["year"], evenements["phase"])])
    ev = ev.dropna(subset=["etat"])
    t = pd.crosstab(ev["cluster"], ev["etat"].astype(int))
    clusters = {}
    for k, ligne in t.iterrows():
        total = int(ligne.sum())
        dominant = int(ligne.idxmax())
        part = float(ligne.max() / total) if total else 0.0
        rattache = part >= SEUIL_RATTACHEMENT
        clusters[int(k)] = {
            "etat_id": dominant if rattache else None,
            "etat": noms[dominant] if rattache else "mixte",
            "etat_dominant": noms[dominant],
            "part": round(part, 3), "n_evenements": total,
            "repartition": {noms[int(e)]: int(n) for e, n in ligne.items() if n},
        }
    v = None
    if t.shape[0] > 1 and t.shape[1] > 1:
        from scipy.stats import chi2_contingency
        chi2 = chi2_contingency(t)[0]
        v = round(float(np.sqrt(chi2 / (t.values.sum() * (min(t.shape) - 1)))), 3)
    etats = []
    for e in donnees["etats"]:
        enfants = sorted(k for k, c in clusters.items() if c["etat_id"] == e["id"])
        etats.append(dict(e, clusters=enfants,
                          n_evenements=int(sum(clusters[k]["n_evenements"] for k in enfants))))
    return {"phase": phase, "etats": etats, "clusters": clusters, "cramer_v": v,
            "tableau": {int(k): {noms[int(e)]: int(n) for e, n in l.items()}
                        for k, l in t.iterrows()},
            "seuil_rattachement": SEUIL_RATTACHEMENT}


def etat_du_cluster(cluster, phase="All_phases", donnees=None):
    """(nom de l'etat, part) du cluster, ou (None, None) si indisponible."""
    try:
        c = hierarchie(phase, donnees)["clusters"].get(int(cluster))
    except EtatsIndisponibles:
        return None, None
    if not c:
        return None, None
    return c["etat"], c["part"]


if __name__ == "__main__":
    s = construire()
    for e in s["etats"]:
        print(("%-26s id=%d  %2d saisons  Nino34 %+.2f  IOBM %+.2f" % (
            e["nom"], e["id"], e["n_saisons"], e["indices_moyens"]["Nino34"],
            e["indices_moyens"]["IOBM"])).encode("ascii", "replace").decode())
    for ph in ("All_phases",) + PHASES:
        h = hierarchie(ph, s)
        print(ph, "V de Cramer", h["cramer_v"], {k: (c["etat"], c["part"]) for k, c in h["clusters"].items()}
              .__repr__().encode("ascii", "replace").decode())
