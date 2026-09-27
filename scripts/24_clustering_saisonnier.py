#!/usr/bin/env python3
"""Classification des configurations oceaniques, version corrigee (saisonniere).

Pourquoi ce script (27/09/2026): le script 11 classe les 1263 EVENEMENTS.
Diagnostic sur ses sorties:
  - silhouettes 0,06-0,09 aux k retenus (structure quasi absente);
  - le vote designait k=15, la borne testee, dans les 4 phases (k force a la main);
  - 90 % des paires d'evenements d'une meme annee tombent dans le meme cluster
    (22 % au hasard): les evenements d'une saison partagent le meme ocean
    (persistance des SST), les clusters reconnaissent surtout l'ANNEE;
  - stabilite bootstrap ARI ~0,40-0,45;
  - pas de ponderation par la latitude, 90 % de variance = 413 composantes.

Protocole corrige, FIXE AVANT d'en voir les resultats:
  1. Unite = SAISON: composite (moyenne) des champs SST du jour des evenements
     extremes d'une annee et d'une phase. Par phase ~41 saisons independantes;
     "Toutes phases" = unites annee x phase.
  2. Detrend lineaire par pixel (sur l'annee), domaine tropical 30S-40N,
     ponderation sqrt(cos lat), SANS normalisation par pixel (EOF de covariance,
     usage standard: les regions de faible variance ne sont pas amplifiees).
  3. ACP: 10 composantes (sensibilite 5 et 20).
  4. K-Means et Ward (hierarchique), k = 2..8.
  5. Significativite: silhouette comparee a 200 jeux gaussiens de memes
     variances par composante (aucune structure de clusters par construction):
     p = part des jeux nuls qui font aussi bien.
  6. Stabilite: 100 sous-echantillonnages a 80 %, ARI avec la partition complete.
  7. k retenu = le plus stable parmi les k significatifs (p < 0,05, apres
     correction de Holm sur les 7 k testes). Aucun significatif -> on le dit.
  8. Physique: les configurations different-elles par l'intensite des extremes
     de la saison (empreinte = somme des couvertures, pluie max) ? Kruskal-Wallis.

Entree: data/processed/sst_cube_1deg.npz (scripts/19), catalogue des evenements.
Sortie: outputs/clustering_saisonnier/ (JSON, CSV, figures, rapport.md).

Usage: py -3 scripts/24_clustering_saisonnier.py
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from veille.cube import Cube  # noqa: E402

SORTIE = RACINE / "outputs" / "clustering_saisonnier"
EVENEMENTS = RACINE / "data" / "processed" / "extreme_events_phases_senegal.csv"

PHASES = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin", "Toutes_phases"]
K_RANGE = list(range(2, 9))
N_EOF = 10
DOMAINES = {"tropical": (-30, 40), "global": (-60, 60)}
N_NUL = 200
N_BOOT = 100
FRACTION_BOOT = 0.8
SEUIL = 0.05
GRAINE = 42

warnings.filterwarnings("ignore")


# =============================================================================
# Donnees
# =============================================================================
def composites(cube, catalogue):
    """{(annee, phase): champ moyen (120, 360)} sur les jours d'evenements."""
    champs = cube.evenements()
    index = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(cube.evt_dates)}
    cat = catalogue[catalogue["date"].isin(index)]
    sortie = {}
    for (annee, phase), g in cat.groupby(["year", "phase"]):
        pile = champs[[index[d] for d in g["date"]]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sortie[(int(annee), phase)] = np.nanmean(pile, axis=0)
    return sortie


def matrice(comp, unites, lats, domaine):
    """Matrice (n_unites, n_pixels_ocean) detrendee et ponderee, + infos."""
    la0, la1 = DOMAINES[domaine]
    lignes = (lats >= la0) & (lats <= la1)
    X = np.stack([comp[u][lignes].ravel() for u in unites]).astype("float64")
    ok = np.isfinite(X).all(axis=0)
    X = X[:, ok]
    annees = np.array([u[0] for u in unites], dtype="float64")
    yc = annees - annees.mean()
    X = X - np.outer(yc, (yc @ X) / (yc @ yc))          # detrend lineaire par pixel
    X = X - X.mean(axis=0)
    w = np.sqrt(np.cos(np.deg2rad(np.repeat(lats[lignes], comp[unites[0]].shape[1]))))[ok]
    return X * w, {"lignes": lignes, "ok": ok, "w": w, "brut": X}


def eof(Xw, n):
    from sklearn.decomposition import PCA
    pca = PCA(n_components=min(n, Xw.shape[0] - 1), svd_solver="full")
    Z = pca.fit_transform(Xw)
    return Z, pca


# =============================================================================
# Classification et diagnostics
# =============================================================================
def partition(Z, k, methode, graine=GRAINE):
    if methode == "kmeans":
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=k, n_init=20, random_state=graine).fit_predict(Z)
    from sklearn.cluster import AgglomerativeClustering
    return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z)


def silhouette(Z, lab):
    from sklearn.metrics import silhouette_score
    if len(set(lab)) < 2:
        return np.nan
    return float(silhouette_score(Z, lab))


def test_nul(Z, k, methode, obs, rng):
    """Silhouette de jeux gaussiens sans clusters (memes variances par EOF)."""
    ecarts = Z.std(axis=0, ddof=1)
    nul = []
    for _ in range(N_NUL):
        G = rng.normal(size=Z.shape) * ecarts
        nul.append(silhouette(G, partition(G, k, methode, int(rng.integers(1 << 30)))))
    nul = np.array(nul)
    return float((1 + np.sum(nul >= obs)) / (1 + len(nul))), float(np.nanmean(nul))


def stabilite(Z, k, methode, lab, rng):
    from sklearn.metrics import adjusted_rand_score
    n = len(Z)
    m = int(round(FRACTION_BOOT * n))
    aris = []
    for _ in range(N_BOOT):
        idx = np.sort(rng.choice(n, m, replace=False))
        sous = partition(Z[idx], k, methode, int(rng.integers(1 << 30)))
        aris.append(adjusted_rand_score(lab[idx], sous))
    return float(np.mean(aris)), float(np.percentile(aris, 5))


def holm(ps):
    ordre = np.argsort(ps)
    ajust = np.empty(len(ps))
    courant = 0.0
    for rang, i in enumerate(ordre):
        courant = max(courant, (len(ps) - rang) * ps[i])
        ajust[i] = min(1.0, courant)
    return ajust


def evaluer(Z, methode, rng):
    lignes = []
    for k in K_RANGE:
        lab = partition(Z, k, methode)
        s = silhouette(Z, lab)
        p, s_nul = test_nul(Z, k, methode, s, rng)
        ari, ari5 = stabilite(Z, k, methode, lab, rng)
        tailles = np.bincount(lab)
        lignes.append({"k": k, "silhouette": round(s, 3), "silhouette_nulle": round(s_nul, 3),
                       "p": round(p, 4), "stabilite_ari": round(ari, 3),
                       "stabilite_ari_p5": round(ari5, 3), "taille_min": int(tailles.min())})
    t = pd.DataFrame(lignes)
    t["p_holm"] = np.round(holm(t["p"].values), 4)
    return t


def choisir(t):
    ok = t[(t["p_holm"] < SEUIL) & (t["taille_min"] >= 3)]
    if ok.empty:
        return None
    return int(ok.sort_values(["stabilite_ari", "silhouette"], ascending=False).iloc[0]["k"])


def lien_extremes(unites, lab, catalogue):
    """Les configurations different-elles par l'intensite des extremes ?"""
    from scipy.stats import kruskal
    g = catalogue.groupby(["year", "phase"])
    emp = g["coverage_percent"].sum()
    pmax = g["max_precip"].max()
    df = pd.DataFrame({"cluster": lab,
                       "empreinte": [emp.get(u, np.nan) for u in unites],
                       "pluie_max": [pmax.get(u, np.nan) for u in unites]})
    res = {}
    for col in ("empreinte", "pluie_max"):
        groupes = [d[col].dropna().values for _, d in df.groupby("cluster")]
        groupes = [x for x in groupes if len(x) >= 2]
        p = float(kruskal(*groupes).pvalue) if len(groupes) >= 2 else None
        res[col] = {"p_kruskal": None if p is None else round(p, 4),
                    "moyenne_par_cluster": {int(c): round(float(d[col].mean()), 1)
                                            for c, d in df.groupby("cluster")}}
    return res


# =============================================================================
# Figures
# =============================================================================
def figure_diagnostics(tables, chemin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 4, figsize=(15, 6.5), sharex=True)
    couleurs = {"kmeans": "#4F46E5", "ward": "#0EA5E9"}
    for j, phase in enumerate(PHASES):
        for methode, t in tables[phase].items():
            c = couleurs[methode]
            ax = axes[0, j]
            ax.plot(t["k"], t["silhouette"], "-o", color=c, label=methode, ms=4)
            ax.plot(t["k"], t["silhouette_nulle"], ":", color=c, alpha=.7)
            sig = t[t["p_holm"] < SEUIL]
            ax.scatter(sig["k"], sig["silhouette"], s=90, facecolors="none", edgecolors=c)
            axes[1, j].plot(t["k"], t["stabilite_ari"], "-o", color=c, ms=4)
        axes[0, j].set_title(phase.replace("_", " "), fontsize=10)
        axes[1, j].set_xlabel("k")
        axes[1, j].set_ylim(0, 1)
    axes[0, 0].set_ylabel("silhouette\n(pointilles: hasard)")
    axes[1, 0].set_ylabel("stabilite (ARI)")
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.suptitle("Clustering saisonnier: silhouette vs hasard (cercle = significatif, Holm) "
                 "et stabilite bootstrap", fontsize=11)
    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)


def figure_centroides(phase, unites, lab, info, cube, domaine, chemin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    brut = info["brut"]                                   # detrende, non pondere
    lignes, ok = info["lignes"], info["ok"]
    lats = cube.lats[lignes]
    k = int(lab.max()) + 1
    fig, axes = plt.subplots(k, 1, figsize=(10, 2.3 * k), squeeze=False)
    for c in range(k):
        champ = np.full(ok.size, np.nan)
        champ[ok] = brut[lab == c].mean(axis=0)
        z = champ.reshape(lignes.sum(), cube.lons.size)
        ax = axes[c, 0]
        im = ax.pcolormesh(cube.lons, lats, z, cmap="RdBu_r", vmin=-0.8, vmax=0.8, shading="nearest")
        ax.plot(-17.4, 14.7, "*", color="#F59E0B", ms=9, mec="k", mew=.4)
        ans = sorted(u[0] for u, l in zip(unites, lab) if l == c)
        ax.set_title("C%d - %d saisons: %s" % (c, len(ans), ", ".join(map(str, ans))), fontsize=8)
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axes[:, 0], shrink=.6, label="anomalie SST detrendee (degC)")
    fig.suptitle("%s - configurations (composites, domaine %s)" % (phase, domaine), fontsize=10)
    fig.savefig(chemin, dpi=110, bbox_inches="tight")
    plt.close(fig)


# =============================================================================
def main():
    rng = np.random.default_rng(GRAINE)
    SORTIE.mkdir(parents=True, exist_ok=True)
    cube = Cube.charger()
    cat = pd.read_csv(EVENEMENTS, usecols=["date", "year", "phase", "coverage_percent",
                                           "max_precip"])
    comp = composites(cube, cat)

    resume, tables, sensib = {}, {}, []
    for phase in PHASES:
        unites = sorted(u for u in comp if phase == "Toutes_phases" or u[1] == phase)
        Xw, info = matrice(comp, unites, cube.lats, "tropical")
        Z, pca = eof(Xw, N_EOF)
        tables[phase] = {}
        resume[phase] = {"n_saisons": len(unites),
                         "variance_expliquee_10_eof": round(float(pca.explained_variance_ratio_.sum()), 3),
                         "methodes": {}}
        for methode in ("kmeans", "ward"):
            print("%s / %s ..." % (phase, methode), flush=True)
            t = evaluer(Z, methode, rng)
            tables[phase][methode] = t
            t.to_csv(SORTIE / ("%s_%s.csv" % (phase, methode)), index=False)
            k = choisir(t)
            bloc = {"k_retenu": k, "tableau": t.to_dict(orient="records")}
            if k is not None:
                lab = partition(Z, k, methode)
                bloc["lien_extremes"] = lien_extremes(unites, lab, cat)
                bloc["saisons_par_cluster"] = {
                    int(c): ["%d%s" % (u[0], "" if phase != "Toutes_phases"
                                      else "-P" + str(PHASES.index(u[1]) + 1))
                             for u, l in zip(unites, lab) if l == c]
                    for c in range(k)}
                if methode == "kmeans" or resume[phase].get("figure") is None:
                    figure_centroides(phase, unites, lab, info, cube, "tropical",
                                      SORTIE / ("%s_%s_centroides.png" % (phase, methode)))
            resume[phase]["methodes"][methode] = bloc

        # Sensibilite: nombre d'EOF et domaine (K-Means, meilleure silhouette signif.)
        for domaine in DOMAINES:
            X2, _ = matrice(comp, unites, cube.lats, domaine)
            for n in (5, 10, 20):
                if domaine == "tropical" and n == N_EOF:
                    t = tables[phase]["kmeans"]
                else:
                    Z2, _ = eof(X2, n)
                    t = evaluer(Z2, "kmeans", rng)
                sensib.append({"phase": phase, "domaine": domaine, "n_eof": n,
                               "k_significatifs": [int(k) for k in t[t["p_holm"] < SEUIL]["k"]],
                               "silhouette_max": float(t["silhouette"].max()),
                               "p_holm_min": float(t["p_holm"].min()),
                               "k_retenu": choisir(t)})
                print("   sensibilite %s %s EOF=%d -> %s" % (phase, domaine, n, sensib[-1]["k_retenu"]),
                      flush=True)

    figure_diagnostics(tables, SORTIE / "diagnostics.png")
    pd.DataFrame(sensib).to_csv(SORTIE / "sensibilite.csv", index=False)
    json.dump({"protocole": __doc__, "resultats": resume, "sensibilite": sensib},
              open(SORTIE / "resultats.json", "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, default=str)
    rapport(resume, sensib)
    # Etats nommes pour la hierarchie etats -> configurations du script 11.
    from veille import etats
    try:
        etats.construire()
    except etats.EtatsIndisponibles as exc:
        print("[INFO] Etats saisonniers non construits: %s" % exc)
    print("Ecrit dans", SORTIE)


def rapport(resume, sensib):
    L = ["# Clustering saisonnier des configurations oceaniques", "",
         "Protocole: voir en-tete de scripts/24_clustering_saisonnier.py. "
         "Significativite: silhouette vs %d jeux sans structure, correction de Holm sur "
         "k = 2..8. Stabilite: %d sous-echantillons a 80 %%." % (N_NUL, N_BOOT), ""]
    for phase, r in resume.items():
        L += ["## %s (%d saisons, 10 EOF = %.0f %% de variance)" % (
            phase, r["n_saisons"], 100 * r["variance_expliquee_10_eof"]), ""]
        for methode, b in r["methodes"].items():
            L += ["**%s** - k retenu : %s" % (methode, b["k_retenu"] if b["k_retenu"]
                                              else "aucun (pas de structure significative)"), "",
                  "| k | silhouette | hasard | p (Holm) | stabilite ARI |", "|---|---|---|---|---|"]
            for t in b["tableau"]:
                L.append("| %d | %.3f | %.3f | %.3f | %.2f |" % (
                    t["k"], t["silhouette"], t["silhouette_nulle"], t["p_holm"], t["stabilite_ari"]))
            if b.get("lien_extremes"):
                le = b["lien_extremes"]
                L += ["", "Lien avec les extremes (Kruskal-Wallis) : empreinte p = %s, pluie max p = %s"
                      % (le["empreinte"]["p_kruskal"], le["pluie_max"]["p_kruskal"])]
                for c, s in b["saisons_par_cluster"].items():
                    L.append("- C%s : %s" % (c, ", ".join(s)))
            L.append("")
    L += ["## Sensibilite (K-Means)", "", "| phase | domaine | EOF | k significatifs | k retenu |",
          "|---|---|---|---|---|"]
    for s in sensib:
        L.append("| %s | %s | %d | %s | %s |" % (s["phase"], s["domaine"], s["n_eof"],
                                                 s["k_significatifs"] or "-", s["k_retenu"] or "-"))
    (SORTIE / "rapport.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
