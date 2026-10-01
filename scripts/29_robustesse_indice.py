#!/usr/bin/env python3
"""Robustesse de l'indice de risque : sensibilite aux ponderations et validation historique.

1. Sensibilite (departements et arrondissements). Variantes calculees a partir des
   composantes A, E, V deja normalisees (rangs centiles, scripts 26 et 27) :
     geometrique      (A x E x V)^(1/3)                 -- indice publie
     moyenne_simple   (A + E + V) / 3
     alea_x2          (A^2 x E x V)^(1/4)
     exposition_x2    (A x E^2 x V)^(1/4)
     vulnerabilite_x2 (A x E x V^2)^(1/4)
     sans_vulnerabilite (A x E)^(1/2)   (la vulnerabilite est provisoire)
   Mesures : correlation de Spearman entre classements ; zones du top 10 communes a
   toutes les variantes ; amplitude du rang de chaque zone.

2. Validation historique (departements). Zones touchees par les inondations de 2005,
   2009, 2012 et 2020, relevees a la main avec leur source et un extrait dans
   data/raw/inondations/zones_touchees_2005_2009_2012_2020.csv. Certitude A = zone
   nommee comme touchee par un document institutionnel ; B = mention ambigue ou presse.
   Test : les zones touchees ont-elles un indice plus eleve ? AUC (probabilite qu'une
   zone touchee ait un indice superieur a une zone non touchee ; 0,5 = hasard), IC 95 %
   par bootstrap stratifie (5000 tirages), test de Mann-Whitney unilateral.
   Meme test pour chaque composante et pour l'ancienne version de l'indice.

Limite a garder en tete : un inventaire d'inondations documentees n'est pas une carte de
l'alea. Les rapports se concentrent sur les villes et la banlieue de Dakar (ou les
degats et les secours se concentrent), et les petites zones rurales y sont rares.

Entrees : outputs/vulnerabilite/indice_risque_departements.csv, ..._arrondissements.csv,
          data/raw/inondations/zones_touchees_2005_2009_2012_2020.csv
Sorties : outputs/vulnerabilite/robustesse/ (CSV, figures PNG, resume.json)

Usage : py -3 scripts/29_robustesse_indice.py
"""
import json
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr

RACINE = Path(__file__).resolve().parent.parent
VULN = RACINE / "outputs" / "vulnerabilite"
SORTIE = VULN / "robustesse"
INVENTAIRE = RACINE / "data" / "raw" / "inondations" / "zones_touchees_2005_2009_2012_2020.csv"

# nom -> (poids A, poids E, poids V, type de moyenne)
VARIANTES = {
    "geometrique": (1, 1, 1, "geo"),
    "moyenne_simple": (1, 1, 1, "arith"),
    "alea_x2": (2, 1, 1, "geo"),
    "exposition_x2": (1, 2, 1, "geo"),
    "vulnerabilite_x2": (1, 1, 2, "geo"),
    "sans_vulnerabilite": (1, 1, 0, "geo"),
}
LIBELLES = {
    "geometrique": "G\u00e9om\u00e9trique (publi\u00e9)",
    "moyenne_simple": "Moyenne simple",
    "alea_x2": "Al\u00e9a \u00d72",
    "exposition_x2": "Exposition \u00d72",
    "vulnerabilite_x2": "Vuln\u00e9rabilit\u00e9 \u00d72",
    "sans_vulnerabilite": "Sans vuln\u00e9rabilit\u00e9",
}
ANNEES = (2005, 2009, 2012, 2020)
N_BOOT = 5000
GRAINE = 20261001
BLEU, BLEU_FONCE, GRIS = "#2A78D6", "#104281", "#9A9A96"


def variante(t, pa, pe, pv, mode):
    comp = np.column_stack([t["A_alea"], t["E_exposition"], t["V_vulnerabilite"]])
    w = np.array([pa, pe, pv], dtype=float)
    if mode == "arith":
        return comp @ w / w.sum()
    return np.exp(np.log(comp) @ w / w.sum())


def classements(t, nom_col):
    out = t[["pcode", nom_col, "region"]].rename(columns={nom_col: "nom"}).copy()
    for v, (pa, pe, pv, mode) in VARIANTES.items():
        out["score_" + v] = variante(t, pa, pe, pv, mode)
        out["rang_" + v] = out["score_" + v].rank(ascending=False, method="min").astype(int)
    rangs = out[["rang_" + v for v in VARIANTES]]
    out["rang_min"], out["rang_max"] = rangs.min(axis=1), rangs.max(axis=1)
    out["amplitude_rang"] = out["rang_max"] - out["rang_min"]
    return out.sort_values("rang_geometrique").reset_index(drop=True)


def sensibilite(c, niveau):
    noms = list(VARIANTES)
    rho = pd.DataFrame(index=noms, columns=noms, dtype=float)
    for a in noms:
        for b in noms:
            rho.loc[a, b] = spearmanr(c["score_" + a], c["score_" + b]).statistic
    tops = {v: set(c.nsmallest(10, "rang_" + v)["pcode"]) for v in noms}
    communs = set.intersection(*tops.values())
    union = set.union(*tops.values())
    paires = [rho.loc[a, b] for a, b in combinations(noms, 2)]
    return rho, {
        "niveau": niveau,
        "zones": int(len(c)),
        "spearman_min": round(float(min(paires)), 3),
        "spearman_vs_publie_min": round(float(rho.loc["geometrique"].drop("geometrique").min()), 3),
        "top10_communs_toutes_variantes": int(len(communs)),
        "top10_communs": c[c["pcode"].isin(communs)]["nom"].tolist(),
        "top10_union": int(len(union)),
        "amplitude_rang_mediane": float(c["amplitude_rang"].median()),
        "amplitude_rang_max": int(c["amplitude_rang"].max()),
        "zone_amplitude_max": c.loc[c["amplitude_rang"].idxmax(), "nom"],
    }


def auc_ic(pos, neg, rng):
    """AUC = P(pos > neg) + 0,5 P(egalite) ; IC 95 % bootstrap stratifie ; p Mann-Whitney."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)

    def auc(p, n):
        d = p[:, None] - n[None, :]
        return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)

    val = auc(pos, neg)
    boots = [auc(rng.choice(pos, pos.size), rng.choice(neg, neg.size)) for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p = mannwhitneyu(pos, neg, alternative="greater").pvalue
    return val, float(lo), float(hi), float(p)


def validation(dep, inv):
    inconnus = sorted(set(inv["departement"]) - set(dep["departement"]))
    if inconnus:
        raise SystemExit("Departements de l'inventaire absents de l'indice : %s" % inconnus)
    groupes = {}
    for a in ANNEES:
        groupes["%d (A)" % a] = set(inv[(inv["annee"] == a) & (inv["certitude"] == "A")]["departement"])
        groupes["%d (A+B)" % a] = set(inv[inv["annee"] == a]["departement"])
    groupes["au moins une (A)"] = set(inv[inv["certitude"] == "A"]["departement"])
    groupes["au moins une (A+B)"] = set(inv["departement"])
    # Plus de deux evenements : zones touchees de facon recurrente.
    n_ev = inv[inv["certitude"] == "A"].groupby("departement")["annee"].nunique()
    groupes["2 evenements ou plus (A)"] = set(n_ev[n_ev >= 2].index)

    variables = {"indice publi\u00e9": dep["indice_risque"]}
    for v, (pa, pe, pv, mode) in VARIANTES.items():
        if v != "geometrique":
            variables[LIBELLES[v]] = pd.Series(variante(dep, pa, pe, pv, mode), index=dep.index)
    variables.update({"Al\u00e9a seul": dep["A_alea"], "Exposition seule": dep["E_exposition"],
                      "Vuln\u00e9rabilit\u00e9 seule": dep["V_vulnerabilite"],
                      "ancien indice (30/09)": dep["indice_risque_ref"]})
    rng = np.random.default_rng(GRAINE)
    lignes = []
    for g, zones in groupes.items():
        touche = dep["departement"].isin(zones)
        for nom, x in variables.items():
            a, lo, hi, p = auc_ic(x[touche], x[~touche], rng)
            lignes.append({"groupe": g, "variable": nom, "n_touches": int(touche.sum()),
                           "n_autres": int((~touche).sum()), "auc": round(a, 3),
                           "ic95_bas": round(lo, 3), "ic95_haut": round(hi, 3),
                           "p_mann_whitney_unilateral": round(p, 4)})
    rho_nev = spearmanr(dep["departement"].map(n_ev).fillna(0), dep["indice_risque"])
    return pd.DataFrame(lignes), groupes, n_ev, rho_nev


def figure_sensibilite(c, rho, chemin, titre_niveau):
    noms = list(VARIANTES)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7.2), gridspec_kw={"width_ratios": [1, 1.25]})
    im = ax1.imshow(rho.values.astype(float), vmin=0.5, vmax=1, cmap="Blues")
    ax1.set_xticks(range(len(noms)), [LIBELLES[n] for n in noms], rotation=35, ha="right", fontsize=9)
    ax1.set_yticks(range(len(noms)), [LIBELLES[n] for n in noms], fontsize=9)
    for i in range(len(noms)):
        for j in range(len(noms)):
            v = float(rho.values[i, j])
            ax1.text(j, i, ("%.2f" % v).replace(".", ","), ha="center", va="center", fontsize=9,
                     color="white" if v > 0.85 else "#1A1A19")
    ax1.set_title("Corr\u00e9lation de Spearman entre classements\n(%s)" % titre_niveau, fontsize=11)
    fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)

    tops = set()
    for v in noms:
        tops |= set(c.nsmallest(10, "rang_" + v)["pcode"])
    d = c[c["pcode"].isin(tops)].sort_values("rang_geometrique", ascending=False)
    y = np.arange(len(d))
    ax2.hlines(y, d["rang_min"], d["rang_max"], color=GRIS, lw=3, alpha=0.6)
    for v in noms[1:]:
        ax2.scatter(d["rang_" + v], y, s=22, facecolors="white", edgecolors=BLEU, lw=1.2, zorder=3)
    ax2.scatter(d["rang_geometrique"], y, s=46, color=BLEU_FONCE, zorder=4,
                label="indice publi\u00e9 (g\u00e9om\u00e9trique)")
    ax2.scatter([], [], s=22, facecolors="white", edgecolors=BLEU, label="5 autres variantes")
    ax2.axvline(10.5, color="#1A1A19", lw=0.8, ls=":")
    ax2.text(10.7, len(d) - 0.6, "top 10", fontsize=8, color="#1A1A19")
    ax2.set_yticks(y, d["nom"] + " (" + d["region"].astype(str) + ")", fontsize=8.5)
    ax2.set_xlabel("Rang (1 = risque le plus \u00e9lev\u00e9)")
    ax2.set_xlim(0, max(25, d["rang_max"].max() + 2))
    ax2.invert_xaxis()
    ax2.set_title("Rang des zones entrant au moins une fois dans un top 10\n(trait gris : \u00e9cart"
                  " entre la meilleure et la moins bonne variante)", fontsize=11)
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, fontsize=8.5,
               frameon=False)
    ax2.grid(axis="x", color="#E6E5E1", lw=0.6)
    for a in (ax2,):
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(chemin, dpi=160)
    plt.close(fig)


def figure_validation(dep, groupes, val, chemin):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.4), gridspec_kw={"width_ratios": [1.3, 1]})
    cols = ["2005 (A)", "2009 (A)", "2012 (A)", "2020 (A)", "au moins une (A)"]
    rng = np.random.default_rng(1)
    for k, g in enumerate(cols):
        touche = dep["departement"].isin(groupes[g])
        for est, couleur, dx in ((False, GRIS, -0.17), (True, BLEU, 0.17)):
            x = dep.loc[touche == est, "indice_risque"]
            ax1.scatter(k + dx + rng.uniform(-0.07, 0.07, len(x)), x, s=18, color=couleur,
                        alpha=0.85 if est else 0.55, edgecolors="none")
            ax1.hlines(x.median(), k + dx - 0.12, k + dx + 0.12, color="#1A1A19", lw=1.6)
        r = val[(val["groupe"] == g) & (val["variable"] == "indice publi\u00e9")].iloc[0]
        ax1.text(k, 0.98, ("AUC %.2f\n[%.2f ; %.2f]\nn = %d" % (r["auc"], r["ic95_bas"],
                                                                 r["ic95_haut"], r["n_touches"]))
                 .replace(".", ","), ha="center", va="top", fontsize=8.5)
    ax1.scatter([], [], color=GRIS, s=18, label="d\u00e9partements non cit\u00e9s")
    ax1.scatter([], [], color=BLEU, s=18, label="d\u00e9partements cit\u00e9s comme touch\u00e9s")
    ax1.set_xticks(range(len(cols)), ["2005", "2009", "2012", "2020", "au moins\nune fois"])
    ax1.set_ylim(0, 1.0)
    ax1.set_ylabel("Indice de risque publi\u00e9 (0 \u00e0 1)")
    ax1.set_title("Indice des d\u00e9partements touch\u00e9s et non touch\u00e9s\n(certitude A ;"
                  " trait noir : m\u00e9diane)", fontsize=11)
    ax1.legend(loc="lower right", fontsize=8.5, frameon=False)
    ax1.spines[["top", "right"]].set_visible(False)

    g = "au moins une (A)"
    v = val[val["groupe"] == g].iloc[::-1].reset_index(drop=True)
    y = np.arange(len(v))
    ax2.hlines(y, v["ic95_bas"], v["ic95_haut"], color=BLEU, lw=2)
    ax2.scatter(v["auc"], y, color=BLEU_FONCE, s=36, zorder=3)
    ax2.axvline(0.5, color="#1A1A19", lw=0.8, ls=":")
    ax2.text(0.51, -0.75, "hasard (0,5)", fontsize=8)
    ax2.set_yticks(y, v["variable"], fontsize=9)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(-1, len(v) - 0.5)
    ax2.set_xlabel("AUC et IC 95 % (zones cit\u00e9es au moins une fois, certitude A)")
    ax2.set_title("Quel score distingue les d\u00e9partements touch\u00e9s ?", fontsize=11)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(axis="x", color="#E6E5E1", lw=0.6)
    fig.tight_layout()
    fig.savefig(chemin, dpi=160)
    plt.close(fig)


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    dep = pd.read_csv(VULN / "indice_risque_departements.csv", encoding="utf-8")
    arr_p = VULN / "indice_risque_arrondissements.csv"
    resume = {"variantes": {v: {"poids_A_E_V": list(p[:3]), "moyenne": p[3]}
                            for v, p in VARIANTES.items()}}

    niveaux = [("departements", dep, "departement", "46 d\u00e9partements")]
    if arr_p.exists():
        arr = pd.read_csv(arr_p, encoding="utf-8", keep_default_na=False, na_values=[""])
        niveaux.append(("arrondissements", arr, "arrondissement", "125 arrondissements"))
    resume["sensibilite"] = []
    for niveau, t, col, titre in niveaux:
        c = classements(t, col)
        rho, r = sensibilite(c, niveau)
        resume["sensibilite"].append(r)
        c.to_csv(SORTIE / ("sensibilite_classements_%s.csv" % niveau), index=False,
                 encoding="utf-8", float_format="%.4f")
        rho.round(3).to_csv(SORTIE / ("sensibilite_spearman_%s.csv" % niveau), encoding="utf-8")
        figure_sensibilite(c, rho, SORTIE / ("fig_sensibilite_%s.png" % niveau), titre)
        print("%s : Spearman min %.3f, top 10 communs %d (%s)" % (
            niveau, r["spearman_min"], r["top10_communs_toutes_variantes"],
            ", ".join(r["top10_communs"])))

    inv = pd.read_csv(INVENTAIRE, encoding="utf-8")
    val, groupes, n_ev, rho_nev = validation(dep, inv)
    val.to_csv(SORTIE / "validation_auc_departements.csv", index=False, encoding="utf-8")
    zones = dep[["rang", "pcode", "departement", "region", "indice_risque", "A_alea",
                 "E_exposition", "V_vulnerabilite"]].copy()
    for a in ANNEES:
        zones["touche_%d" % a] = zones["departement"].map(
            inv[inv["annee"] == a].groupby("departement")["certitude"].min()).fillna("")
    zones["n_evenements_A"] = zones["departement"].map(n_ev).fillna(0).astype(int)
    zones.to_csv(SORTIE / "validation_zones_touchees.csv", index=False, encoding="utf-8")
    figure_validation(dep, groupes, val, SORTIE / "fig_validation_inondations.png")

    principal = val[val["variable"] == "indice publi\u00e9"].set_index("groupe")
    resume["validation"] = {
        "inventaire": str(INVENTAIRE.relative_to(RACINE)),
        "bootstrap": N_BOOT, "graine": GRAINE,
        "indice_publie": principal[["n_touches", "auc", "ic95_bas", "ic95_haut",
                                    "p_mann_whitney_unilateral"]].to_dict("index"),
        "spearman_nombre_evenements_indice": {"rho": round(float(rho_nev.statistic), 3),
                                              "p": round(float(rho_nev.pvalue), 4)},
    }
    (SORTIE / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(principal[["n_touches", "auc", "ic95_bas", "ic95_haut",
                     "p_mann_whitney_unilateral"]].to_string())
    print("Spearman nb evenements / indice : rho %.3f p %.4f" % (rho_nev.statistic, rho_nev.pvalue))


if __name__ == "__main__":
    main()
