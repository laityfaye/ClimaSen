#!/usr/bin/env python3
"""Effet d'une modulation saisonniere de l'alea par le bulletin de veille (etude, sans
modification de l'indice publie).

Question : peut-on multiplier l'alea par un facteur borne (+/- 10 %) selon le niveau du
bulletin de veille pre-saison (outputs/veille/bulletin_<annee>.json) ?

Le bulletin donne UN niveau pour tout le Senegal (probabilite C3S d'annee extreme). On
teste donc un facteur identique pour les 46 departements :
    faible 0,90 ; normal 1,00 ; eleve 1,10 ; tres eleve 1,10 ; indetermine 1,00
applique (a) aux indicateurs bruts de l'alea, avant la normalisation en rang centile, ou
(b) a la composante A deja normalisee. On mesure la correlation de Spearman avec le
classement de reference et le nombre de departements qui changent de rang.

On dresse aussi le bilan retrospectif des niveaux (1998-2023) face aux saisons observees
extremes (verification de chaque bulletin).

Entrees : outputs/vulnerabilite/indice_risque_departements.csv, outputs/veille/
Sorties : outputs/vulnerabilite/modulation_saisonniere/ (CSV, resume.json)

Usage : py -3 scripts/31_modulation_saisonniere_alea.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RACINE = Path(__file__).resolve().parent.parent
VULN = RACINE / "outputs" / "vulnerabilite"
VEILLE = RACINE / "outputs" / "veille"
SORTIE = VULN / "modulation_saisonniere"
FACTEURS = {"faible": 0.90, "normal": 1.00, "eleve": 1.10, "tres_eleve": 1.10,
            "indetermine": 1.00}


def centile(s):
    return s.rank(pct=True, method="average")


def indice(a, e, v):
    return (a * e * v) ** (1 / 3)


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    t = pd.read_csv(VULN / "indice_risque_departements.csv", encoding="utf-8")
    lignes, classements = [], t[["pcode", "departement", "rang", "indice_risque"]].copy()

    def variantes(f):
        # (a) facteur sur les indicateurs bruts, puis meme normalisation que le script 26
        a_brut = centile((centile(t["jours_anomalie_2sigma_an"] * f)
                          + centile(t["jours_50mm_an"] * f)) / 2)
        # (b) facteur sur la composante normalisee, plafonnee a 1
        a_norm = np.minimum(t["A_alea"] * f, 1.0)
        return {"avant_normalisation": indice(a_brut, t["E_exposition"], t["V_vulnerabilite"]),
                "apres_normalisation": indice(a_norm, t["E_exposition"], t["V_vulnerabilite"])}

    # Reference de chaque variante = son propre calcul avec f = 1 : les valeurs du CSV
    # sont arrondies a 4 decimales, ce qui peut departager autrement des ex aequo.
    base = {k: x.rank(ascending=False, method="min").astype(int)
            for k, x in variantes(1.0).items()}
    for niveau, f in FACTEURS.items():
        for variante, x in variantes(f).items():
            ref_rang = base[variante]
            rang = x.rank(ascending=False, method="min").astype(int)
            classements["rang_%s_%s" % (niveau, variante)] = rang
            classements["indice_%s_%s" % (niveau, variante)] = x.round(4)
            lignes.append({
                "niveau_bulletin": niveau, "facteur_alea": f, "variante": variante,
                "spearman_vs_reference": round(float(spearmanr(rang, ref_rang).statistic), 4),
                "departements_changeant_de_rang": int((rang != ref_rang).sum()),
                "departements_changeant_de_rang_noms": ", ".join(
                    t.loc[rang != ref_rang, "departement"]),
                "variation_indice_mediane_pct": round(
                    float(((x / variantes(1.0)[variante]) - 1).median() * 100), 2),
            })
    effet = pd.DataFrame(lignes)
    effet.to_csv(SORTIE / "effet_classement_par_niveau.csv", index=False, encoding="utf-8")
    classements.to_csv(SORTIE / "classements_par_niveau.csv", index=False, encoding="utf-8")

    # Bilan retrospectif des niveaux du bulletin (bulletins verifies seulement).
    retro = []
    for f in sorted(VEILLE.glob("bulletin_*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        v = b.get("verification")
        if not v:
            continue
        n = b["niveau_risque"]
        retro.append({"annee": b["annee"], "niveau": n["code"],
                      "probabilite_c3s": n.get("probabilite_annee_extreme"),
                      "extreme_observe": bool(v.get("extreme_observe")),
                      "facteur_qui_aurait_ete_applique": FACTEURS[n["code"]]})
    retro = pd.DataFrame(retro)
    retro.to_csv(SORTIE / "bulletins_retrospectifs_niveaux.csv", index=False, encoding="utf-8")
    bilan = (retro.groupby("niveau")["extreme_observe"].agg(["size", "sum"])
             .rename(columns={"size": "saisons", "sum": "saisons_extremes"}))
    bilan["part_extremes_pct"] = (100 * bilan["saisons_extremes"] / bilan["saisons"]).round(1)

    comp = json.loads((VEILLE / "competence_projection.json").read_text(encoding="utf-8"))
    cal = json.loads((VEILLE / "calibration_c3s_ecmwf.json").read_text(encoding="utf-8"))
    var = json.loads((VEILLE / "evaluation_c3s_variantes.json").read_text(encoding="utf-8"))
    actuel = json.loads((VEILLE / "bulletin_2027.json").read_text(encoding="utf-8"))
    resume = {
        "facteurs_testes": FACTEURS,
        "effet_classement": lignes,
        "bilan_retrospectif_1998_2023": bilan.reset_index().to_dict("records"),
        "part_extremes_toutes_saisons_pct": round(100 * retro["extreme_observe"].mean(), 1),
        "annees_extremes_avec_niveau_faible": retro.loc[
            (retro["niveau"] == "faible") & retro["extreme_observe"], "annee"].tolist(),
        "competence": {
            "projection_prevision_reelle": comp["prevision_reelle"],
            "c3s_ecmwf_calibre": cal["competence"],
            "c3s_variantes": [{"variante": r["variante"], "n_modeles": r["n_modeles"],
                               "auc": r["competence"]["auc"],
                               "p": r["competence"]["p_permutation"]}
                              for r in var["resultats"]],
        },
        "bulletin_courant": {"annee": actuel["annee"], "statut": actuel["statut"],
                             "niveau": actuel["niveau_risque"]["code"]},
    }
    (SORTIE / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2,
                                                   default=str), encoding="utf-8")
    print(effet.to_string(index=False))
    print(bilan.to_string())
    print("Part d'annees extremes, toutes saisons verifiees : %.1f %%"
          % resume["part_extremes_toutes_saisons_pct"])
    print("Annees extremes avec un niveau faible :", resume["annees_extremes_avec_niveau_faible"])


if __name__ == "__main__":
    main()
