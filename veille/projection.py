"""Projection de l'etat oceanique novembre-avril sur les configurations de reference.

Les configurations de reference sont celles du memoire: K-Means (toutes
phases, k=9) sur le champ SST global du jour de chaque evenement extreme,
apres detrend lineaire par pixel, normalisation et PCA a 90 % de variance
(scripts/11_kmeans_sst_analysis.py).

Trois produits:
  1. ressemblance_memoire(): correlation de motif entre l'etat nov-avr et
     chacun des 9 centroides DU MEMOIRE (outputs/clustering/All_phases).
     Descriptif: "l'ocean ressemble a la configuration C4".
  2. annees_analogues(): les annees passees dont l'etat nov-avr ressemble le
     plus, et ce qu'a donne leur saison.
  3. Modele: regression logistique sur les ressemblances aux configurations
     (variante V2 du test), qui donne une probabilite d'annee extreme.
     EXPERIMENTAL: sa competence est mesuree par evaluer() et doit toujours
     accompagner la probabilite.

Pourquoi le modele reconstruit les configurations au lieu d'utiliser celles
du memoire: les clusters du memoire ont vu toutes les annees. Evaluer ou
prevoir l'annee N avec eux, c'est utiliser des evenements de l'annee N
(fuite). Le modele refait donc le K-Means sur les seules annees
d'apprentissage, avec la meme procedure, a 1 deg (accord avec le memoire:
ARI 0,58 sur 1983-2023).
"""
import warnings

import numpy as np
import pandas as pd

from . import CLUSTERING, INONDATIONS_CONNUES
from . import annees as mod_annees
from .cube import CubeIndisponible, reduire

PHASE_REFERENCE = "All_phases"
K_REFERENCE = 9
VARIANCE_PCA = 0.90
C_LOGISTIQUE = 0.5
DEBUT_ETAT = 1984          # pas de novembre 1982 dans OISST
DEBUT_PREVISION_REELLE = 1998


def _poids(cube, masque):
    w = np.sqrt(np.cos(np.deg2rad(np.repeat(cube.lats, cube.lons.size))))
    return w[masque]


def _correlation(champs, vecteur, w):
    """Correlation de motif ponderee (cos lat) entre chaque ligne et vecteur."""
    a = (vecteur - vecteur.mean()) * w
    c = (champs - champs.mean(1, keepdims=True)) * w
    return (c @ a) / (np.linalg.norm(c, axis=1) * np.linalg.norm(a))


class Contexte:
    """Donnees communes: evenements du memoire, masque ocean, cible annuelle."""

    def __init__(self, cube, phase=PHASE_REFERENCE):
        self.cube = cube
        ref = pd.read_csv(CLUSTERING / phase / ("%s_events_with_clusters.csv" % phase),
                          parse_dates=["date"])
        pos = {d: i for i, d in enumerate(cube.evt_dates)}
        ref = ref[ref["date"].isin(pos)].reset_index(drop=True)
        if len(ref) < 100:
            raise CubeIndisponible("Trop peu d'evenements du memoire dans le cube (%d)." % len(ref))
        self.ref = ref
        champs = cube.evenements()[[pos[d] for d in ref["date"]]]
        champs = champs.reshape(len(ref), -1)
        # Masque ocean commun a tous les evenements et a tous les mois.
        self.masque = np.isfinite(champs).all(0) & cube.pixels_toujours_valides()
        self.X_evt = champs[:, self.masque].astype(np.float64)
        self.annees_evt = ref["year"].values
        self.w = _poids(cube, self.masque)
        self.empreinte = mod_annees.empreinte()

    def etat(self, annee, partiel=False):
        if partiel:
            mois = [m for m in self.cube.mois_etat(annee) if self.cube.a_le_mois(*m)]
            if not mois:
                raise CubeIndisponible("Aucun mois de novembre-avril disponible pour %d." % annee)
            champ = np.mean([self.cube.mensuel(a, m) for a, m in mois], axis=0)
        else:
            champ = self.cube.etat(annee)
        return champ.reshape(-1)[self.masque].astype(np.float64)

    def annees_etat(self):
        return [a for a in self.cube.annees_etat_complet() if a >= DEBUT_ETAT]

    def annees_observees(self):
        """Annees dont on connait a la fois l'etat et le resultat de la saison."""
        fin = int(self.empreinte.index.max())
        return [a for a in self.annees_etat() if a <= fin]


class Configurations:
    """Reproduction du K-Means du memoire sur les annees d'apprentissage."""

    def __init__(self, ctx, annees_app, k=K_REFERENCE):
        sel = np.isin(ctx.annees_evt, list(annees_app))
        X = ctx.X_evt[sel]
        annees = ctx.annees_evt[sel].astype(float)
        self.ybar = annees.mean()
        yc = annees - self.ybar
        self.pente = (yc @ X) / (yc @ yc)
        Xd = X - np.outer(yc, self.pente)
        self.mu = Xd.mean(0)
        self.sd = Xd.std(0)
        self.sd[self.sd == 0] = 1
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        Z = (Xd - self.mu) / self.sd
        self.pca = PCA(n_components=VARIANCE_PCA, svd_solver="full").fit(Z)
        self.km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(self.pca.transform(Z))
        self.labels = self.km.labels_
        self.annees = ctx.annees_evt[sel]
        cent = self.pca.inverse_transform(self.km.cluster_centers_) * self.sd + self.mu
        self.centroides = cent
        self.w = ctx.w

    def detrend(self, champ, annee):
        return champ - self.pente * (annee - self.ybar)

    def ressemblances(self, champ, annee):
        return _correlation(self.centroides, self.detrend(champ, annee), self.w)


class Modele:
    """V2: logistique sur les ressemblances aux configurations (apprentissage donne)."""

    def __init__(self, ctx, annees_app):
        from sklearn.linear_model import LogisticRegression
        annees_app = sorted(annees_app)
        self.annees_app = annees_app
        self.seuil = mod_annees.seuil(ctx.empreinte, annees_app)
        self.base = float(np.mean([ctx.empreinte.loc[a] > self.seuil for a in annees_app]))
        # Les configurations voient les evenements de toutes les annees
        # d'apprentissage (1983 compris); la calibration, les annees avec etat.
        self.configs = Configurations(ctx, annees_app)
        cal = [a for a in annees_app if a >= DEBUT_ETAT]
        R = np.array([self.configs.ressemblances(ctx.etat(a), a) for a in cal])
        y = np.array([int(ctx.empreinte.loc[a] > self.seuil) for a in cal])
        if y.min() == y.max():
            raise ValueError("Apprentissage sans les deux classes.")
        self.lr = LogisticRegression(C=C_LOGISTIQUE).fit(R, y)

    def probabilite(self, champ, annee):
        r = self.configs.ressemblances(champ, annee)
        return float(self.lr.predict_proba(r[None])[0, 1])


# =============================================================================
# Produits descriptifs
# =============================================================================
def centroides_memoire(ctx, phase=PHASE_REFERENCE):
    """Centroides SST du memoire (0,25 deg) ramenes a la grille du cube."""
    brut = np.load(CLUSTERING / phase / ("%s_centroids_sst.npy" % phase))
    k = brut.shape[0]
    grille = reduire(brut.reshape(k, 480, 1440).astype("float32"))
    return grille.reshape(k, -1)[:, ctx.masque].astype(np.float64)


def profil_configurations(ctx, phase=PHASE_REFERENCE):
    """Pour chaque configuration du memoire: annees, evenements, part en annee extreme."""
    table, s = mod_annees.classement(ctx.empreinte)
    ref = ctx.ref
    profil = {}
    for k, g in ref.groupby("cluster"):
        ans = g["year"].value_counts()
        profil[int(k)] = {
            "n_evenements": int(len(g)),
            "annees_principales": [int(a) for a in ans.index[:5]],
            "part_evenements_en_annee_extreme": round(float(
                g["year"].map(table["extreme"]).fillna(False).mean()), 2),
        }
    return profil


def ressemblance_memoire(ctx, champ, annee, reference):
    """Correlation de motif avec chaque configuration du memoire, triee."""
    pente = reference.configs.pente
    ybar = reference.configs.ybar
    r = _correlation(centroides_memoire(ctx), champ - pente * (annee - ybar), ctx.w)
    profil = profil_configurations(ctx)
    ordre = np.argsort(-r)
    return [dict(configuration=int(k), correlation=round(float(r[k]), 3), **profil.get(int(k), {}))
            for k in ordre]


def annees_analogues(ctx, champ, annee, reference, nombre=5, avant=None):
    """Annees observees dont l'etat nov-avr (detrende) ressemble le plus.

    avant: ne retenir que les annees anterieures (bulletin retrospectif: on
    ne connaissait pas encore les saisons suivantes)."""
    table, s = mod_annees.classement(ctx.empreinte)
    cfg = reference.configs
    cible = cfg.detrend(champ, annee)
    candidats = [a for a in ctx.annees_observees()
                 if a != annee and (avant is None or a < avant)]
    if not candidats:
        return []
    etats = np.array([cfg.detrend(ctx.etat(a), a) for a in candidats])
    r = _correlation(etats, cible, ctx.w)
    ordre = np.argsort(-r)[:nombre]
    return [{"annee": int(candidats[i]), "correlation": round(float(r[i]), 3),
             "empreinte": float(table.loc[candidats[i], "empreinte"]),
             "extreme": bool(table.loc[candidats[i], "extreme"]),
             "inondation_documentee": candidats[i] in INONDATIONS_CONNUES}
            for i in ordre]


# =============================================================================
# Competence
# =============================================================================
def _scores(res, rng):
    from sklearn.metrics import roc_auc_score
    O = np.array([r["observe"] for r in res])
    P = np.array([r["probabilite"] for r in res])
    B = np.array([r["base"] for r in res])
    if O.min() == O.max():
        return {"calculable": False}
    auc = roc_auc_score(O, P)
    perm = np.array([roc_auc_score(rng.permutation(O), P) for _ in range(2000)])
    return {"calculable": True, "n": int(len(O)), "annees_extremes": int(O.sum()),
            "auc": round(float(auc), 3),
            "p_permutation": round(float((perm >= auc).mean()), 4),
            "brier_skill_score": round(float(1 - np.mean((P - O) ** 2) / np.mean((B - O) ** 2)), 3)}


def evaluer(ctx, journal=print):
    """Competence du modele, sans fuite d'information.

    LOYO: l'annee testee est exclue du K-Means, du seuil et de la calibration.
    PREVISION REELLE: seules les annees anterieures servent (la situation du
    bulletin). C'est ce second chiffre qui dit si la projection peut servir
    seule a prevoir; le premier dit s'il existe un signal physique.
    """
    rng = np.random.default_rng(0)
    observees = ctx.annees_observees()
    toutes = [a for a in ctx.empreinte.index if a >= 1983 and a <= max(observees)]
    sortie = {}
    for nom, test, app in (
            ("loyo", observees, lambda t: [a for a in toutes if a != t]),
            ("prevision_reelle", [a for a in observees if a >= DEBUT_PREVISION_REELLE],
             lambda t: [a for a in toutes if a < t])):
        res = []
        for t in test:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m = Modele(ctx, app(t))
                p = m.probabilite(ctx.etat(t), t)
            res.append({"annee": int(t), "probabilite": round(p, 3), "base": round(m.base, 3),
                        "observe": int(ctx.empreinte.loc[t] > m.seuil)})
            journal("  %s %d  p=%.2f  observe=%d" % (nom, t, p, res[-1]["observe"]))
        sortie[nom] = dict(_scores(res, rng), annees=res)
    pr = sortie["prevision_reelle"]
    signal = sortie["loyo"].get("p_permutation", 1) < 0.05
    previsible = pr.get("p_permutation", 1) < 0.05 and pr.get("brier_skill_score", -1) > 0
    sortie["verdict"] = (
        "competence demontree en prevision reelle" if previsible else
        "signal physique present (validation LOYO) mais pas de competence demontree en "
        "prevision reelle: indication experimentale seulement" if signal else
        "pas de competence demontree")
    sortie["utilisable_seule"] = bool(previsible)
    sortie["methode"] = ("V2: regression logistique (C=%.1f) sur les correlations de motif entre "
                         "l'etat SST nov-avr detrende et les %d configurations K-Means "
                         "reconstruites sur les annees d'apprentissage." % (C_LOGISTIQUE, K_REFERENCE))
    return sortie
