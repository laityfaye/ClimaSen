# -*- coding: utf-8 -*-
"""Carnet de fiabilite: ce que les bulletins auraient annonce, et ce qui est arrive.

Chaque bulletin retrospectif (veille.production, --retro) n'utilise que ce
qui etait connu en avril de son annee et porte sa verification CHIRPS. Le
carnet les confronte: detections, fausses alertes, inondations manquees,
AUC et score de Brier. C'est ce qui rend le bulletin credible, ou qui
montre ses limites, face a un decideur.

Une ALERTE est un niveau "eleve" ou "tres eleve".
"""
import numpy as np

from . import production

ALERTES = ("eleve", "tres_eleve")


def _auc(obs, probs):
    obs, probs = np.asarray(obs), np.asarray(probs, dtype=float)
    pos, neg = probs[obs == 1], probs[obs == 0]
    if not len(pos) or not len(neg):
        return None
    # Probabilite qu'une saison extreme recoive une probabilite plus haute
    # qu'une saison normale (ex aequo = 1/2): definition de l'AUC.
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return round(float(gt + eq / 2), 3)


def _brier_skill(obs, probs, base=1 / 3):
    obs, probs = np.asarray(obs, dtype=float), np.asarray(probs, dtype=float)
    ref = np.mean((base - obs) ** 2)
    return round(float(1 - np.mean((probs - obs) ** 2) / ref), 3) if ref else None


def saisons():
    """Une ligne par bulletin verifie, du plus ancien au plus recent."""
    lignes = []
    for annee in sorted(production.bulletins_disponibles()):
        b = production.lire_bulletin(annee)
        v = b.get("verification") if b else None
        if not v:
            continue
        n = b["niveau_risque"]
        p = b.get("projection") or {}
        c = b.get("c3s") or {}
        lignes.append({
            "annee": annee,
            "niveau": n["code"], "libelle": n["libelle"],
            "probabilite_c3s": c.get("probabilite_annee_extreme") if c.get("disponible") else None,
            "probabilite_projection": p.get("probabilite_experimentale"),
            "configuration": (p.get("configurations") or [{}])[0].get("configuration"),
            "extreme_observe": v["extreme_observe"],
            "inondation_documentee": v["inondation_documentee"],
            "rang": v["rang"],
            "verdict": _verdict(n["code"], v["extreme_observe"]),
        })
    return lignes


def _verdict(niveau, extreme):
    if niveau == "indetermine":
        return "sans niveau"
    alerte = niveau in ALERTES
    if alerte and extreme:
        return "détection"
    if alerte:
        return "fausse alerte"
    if extreme:
        return "manquée"
    return "calme confirmé"


def carnet():
    lignes = saisons()
    if not lignes:
        return {"disponible": False, "raison": "aucun bulletin rétrospectif vérifié"}
    avec = [l for l in lignes if l["niveau"] != "indetermine"]
    obs = [int(l["extreme_observe"]) for l in avec]
    compte = {k: sum(1 for l in avec if l["verdict"] == k)
              for k in ("détection", "fausse alerte", "manquée", "calme confirmé")}
    alertes = compte["détection"] + compte["fausse alerte"]
    extremes = compte["détection"] + compte["manquée"]
    proj = [l for l in lignes if l["probabilite_projection"] is not None]
    return {
        "disponible": True,
        "periode": [lignes[0]["annee"], lignes[-1]["annee"]],
        "n_saisons": len(lignes),
        "niveau_de_risque": {
            "n_saisons_avec_niveau": len(avec),
            "comptes": compte,
            "taux_detection": round(compte["détection"] / extremes, 2) if extremes else None,
            "part_fausses_alertes": round(compte["fausse alerte"] / alertes, 2) if alertes else None,
            "auc_probabilite_c3s": _auc(obs, [l["probabilite_c3s"] for l in avec])
            if avec and all(l["probabilite_c3s"] is not None for l in avec) else None,
            "brier_skill_score_c3s": _brier_skill(obs, [l["probabilite_c3s"] for l in avec])
            if avec and all(l["probabilite_c3s"] is not None for l in avec) else None,
        },
        "projection_experimentale": {
            "n": len(proj),
            "auc": _auc([int(l["extreme_observe"]) for l in proj],
                        [l["probabilite_projection"] for l in proj]) if proj else None,
            "brier_skill_score": _brier_skill([int(l["extreme_observe"]) for l in proj],
                                              [l["probabilite_projection"] for l in proj])
            if proj else None,
        },
        "inondations_documentees": [
            {"annee": l["annee"], "niveau": l["libelle"], "verdict": l["verdict"]}
            for l in lignes if l["inondation_documentee"]],
        "fausses_alertes": [l["annee"] for l in lignes if l["verdict"] == "fausse alerte"],
        "lecture": ("AUC 0,5 = hasard, 1 = parfait. Brier skill score > 0 = mieux que "
                    "d'annoncer toujours la fréquence de référence (1 sur 3). Une alerte = "
                    "niveau élevé ou très élevé."),
        "saisons": lignes,
    }


def saison(annee):
    for l in saisons():
        if l["annee"] == int(annee):
            return l
    return None


def comparer(a, b):
    """Deux saisons cote a cote: bulletin, ocean, verification."""
    sortie = {}
    for annee in (int(a), int(b)):
        bul = production.lire_bulletin(annee)
        if not bul:
            sortie[str(annee)] = {"disponible": False}
            continue
        p = bul.get("projection") or {}
        c = bul.get("c3s") or {}
        sortie[str(annee)] = {
            "disponible": True,
            "niveau": bul["niveau_risque"]["libelle"],
            "probabilite": bul["niveau_risque"]["probabilite_annee_extreme"],
            "c3s_anomalie_jas": c.get("anomalie_standardisee") if c.get("disponible") else None,
            "projection_experimentale": p.get("probabilite_experimentale"),
            "configuration_dominante": (p.get("configurations") or [{}])[0],
            "analogues": [x["annee"] for x in p.get("analogues") or []],
            "verification": bul.get("verification"),
        }
    return sortie
