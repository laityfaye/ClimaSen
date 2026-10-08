"""Artefacts compacts d'un bulletin, lisibles sans le cube SST ni scikit-learn.

Le serveur n'a ni les 42 Go d'OISST ni le cube de 77 Mo. Pour que Jarvis
montre l'ocean et explore des scenarios, la production du bulletin
(veille.production) depose a cote du JSON:

  - etats/etat_<annee>.npz: l'anomalie SST novembre-avril BRUTE (non
    detrendee: ce que l'ocean etait vraiment), grille 2 deg 60S-60N;
  - scenarios/kit_<annee>.npz: tout ce qu'il faut pour recalculer la
    projection d'un etat perturbe ("et si l'Atlantique etait plus chaud de
    0,5 degC ?"): etat, pente de detrend, centroides reconstruits et du
    memoire, coefficients de la logistique, etats des annees analogues,
    composites des familles d'oceans des saisons extremes (veille.familles).
    Recalcul en numpy pur, quelques millisecondes.

La trajectoire mensuelle (novembre, novembre-decembre, ...) est calculee a
la production et rangee dans le JSON du bulletin (projection.trajectoire).
"""
import numpy as np

from . import DOSSIER_SORTIE
from . import familles

DOSSIER_ETATS = DOSSIER_SORTIE / "etats"
DOSSIER_KITS = DOSSIER_SORTIE / "scenarios"
ECHELLE = 100.0
VIDE = -32768

# Boites perturbables d'un scenario (lon0, lon1, lat0, lat1), memes bornes
# que les indices du memoire (jarvis/cartes BOITES_RESUME).
BOITES_SCENARIO = {
    "TNA": [(-55, -15, 5, 23)],
    "TSA": [(-30, 10, -20, 0)],
    "ATL3": [(-20, 0, -3, 3)],
    "AMO": [(-80, 0, 0, 60)],
    "Nino34": [(-170, -120, -5, 5)],
    "Nino12": [(-90, -80, -10, 0)],
    "Nino4": [(160, 180, -5, 5), (-180, -150, -5, 5)],
    "IOD_ouest": [(50, 70, -10, 10)],
    "IOD_est": [(90, 110, -10, 0)],
    "IOBM": [(40, 100, -20, 20)],
}
LIBELLES_BOITES = {
    "TNA": "Atlantique tropical nord", "TSA": "Atlantique tropical sud",
    "ATL3": "Atlantique équatorial (ATL3)", "AMO": "Atlantique nord (bassin AMO)",
    "Nino34": "Pacifique central (Niño 3.4)", "Nino12": "Pacifique est (Niño 1+2)",
    "Nino4": "Pacifique ouest (Niño 4)", "IOD_ouest": "océan Indien ouest",
    "IOD_est": "océan Indien est", "IOBM": "bassin de l'océan Indien",
}


class ArtefactIndisponible(Exception):
    pass


# =============================================================================
# Carte de l'etat oceanique
# =============================================================================
def grille_2deg(champ_1deg):
    """(120, 360) a 1 deg -> (60, 180) a 2 deg (moyenne des pixels d'ocean)."""
    import warnings
    g = np.asarray(champ_1deg, dtype="float64").reshape(60, 2, 180, 2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(g, axis=(1, 3))


def sauver_etat(annee, champ_1deg, lats_1deg, lons_1deg, mois):
    DOSSIER_ETATS.mkdir(parents=True, exist_ok=True)
    g = grille_2deg(champ_1deg)
    q = np.clip(np.round(g * ECHELLE), -32767, 32767)
    q[~np.isfinite(g)] = VIDE
    np.savez_compressed(
        DOSSIER_ETATS / ("etat_%d.npz" % annee), anomalie=q.astype("int16"),
        lats=np.asarray(lats_1deg).reshape(60, 2).mean(1).astype("float32"),
        lons=np.asarray(lons_1deg).reshape(180, 2).mean(1).astype("float32"),
        mois=np.array(["%d-%02d" % m for m in mois]))


def charger_etat(annee):
    """(anomalie 2D degC avec NaN, lats, lons, liste des mois 'AAAA-MM')."""
    chemin = DOSSIER_ETATS / ("etat_%d.npz" % int(annee))
    if not chemin.is_file():
        raise ArtefactIndisponible("Pas de carte de l'état océanique pour %d." % annee)
    z = np.load(chemin)
    a = z["anomalie"].astype("float64") / ECHELLE
    a[z["anomalie"] == VIDE] = np.nan
    return a, z["lats"].astype("float64"), z["lons"].astype("float64"), list(z["mois"])


def lons_180(lons):
    """Longitudes ramenees a -180..180. Les fichiers OISST du projet le sont
    deja (verifie: le Sahara tombe a 10 E); garde-fou si une annee future
    arrivait en 0..360."""
    return np.where(lons > 180, lons - 360, lons)


def moyenne_boites(grille2d, lats, lons, boites):
    lo = lons_180(lons)
    valeurs = []
    for lon0, lon1, lat0, lat1 in boites:
        mi = (lats >= lat0) & (lats <= lat1)
        mj = (lo >= lon0) & (lo <= lon1)
        valeurs.append(grille2d[np.ix_(mi, mj)].ravel())
    tout = np.concatenate(valeurs)
    tout = tout[np.isfinite(tout)]
    return float(tout.mean()) if tout.size else None


# =============================================================================
# Kit de scenario
# =============================================================================
def sauver_kit(annee, ctx, modele, champ, centroides_memoire, analogues_annees,
               familles_prep=None):
    """Tout ce qu'il faut pour reprojeter un etat perturbe, sans le cube."""
    from .projection import DEBUT_ETAT  # noqa: F401  (meme periode que le modele)
    DOSSIER_KITS.mkdir(parents=True, exist_ok=True)
    cfg = modele.configs
    etats = np.array([cfg.detrend(ctx.etat(a), a) for a in analogues_annees], dtype="float16")
    np.savez_compressed(
        DOSSIER_KITS / ("kit_%d.npz" % annee),
        annee=np.int32(annee), masque=ctx.masque,
        lats=ctx.cube.lats, lons=ctx.cube.lons,
        etat=champ.astype("float32"), ybar=np.float64(cfg.ybar),
        pente=cfg.pente.astype("float32"), w=ctx.w.astype("float32"),
        centroides=cfg.centroides.astype("float16"),
        centroides_memoire=np.asarray(centroides_memoire, dtype="float16"),
        coef=modele.lr.coef_[0].astype("float64"), intercept=np.float64(modele.lr.intercept_[0]),
        annees_candidates=np.array(analogues_annees, dtype="int32"), etats_candidats=etats,
        **familles.vers_kit(familles_prep))


def completer_kit_familles(annee, familles_prep):
    """Ajoute les familles a un kit deja ecrit (sans refaire le modele).
    Renvoie False s'il n'y a pas de kit pour cette annee."""
    chemin = DOSSIER_KITS / ("kit_%d.npz" % int(annee))
    if not chemin.is_file():
        return False
    kit = {k: v for k, v in charger_kit(annee).items() if not k.startswith("fam_")}
    kit.update(familles.vers_kit(familles_prep))
    tmp = chemin.with_name(chemin.stem + "_tmp.npz")
    np.savez_compressed(tmp, **kit)
    tmp.replace(chemin)
    return True


def charger_kit(annee):
    chemin = DOSSIER_KITS / ("kit_%d.npz" % int(annee))
    if not chemin.is_file():
        raise ArtefactIndisponible("Pas de kit de scénario pour %d." % annee)
    z = np.load(chemin)
    return {k: z[k] for k in z.files}


def _correlation(champs, vecteur, w):
    a = (vecteur - vecteur.mean()) * w
    c = (champs - champs.mean(1, keepdims=True)) * w
    return (c @ a) / (np.linalg.norm(c, axis=1) * np.linalg.norm(a))


def perturber(kit, deltas):
    """Etat du kit + delta (degC) uniforme dans chaque boite demandee."""
    etat = kit["etat"].astype("float64").copy()
    lats = np.repeat(kit["lats"].astype("float64"), kit["lons"].size)[kit["masque"]]
    lons = lons_180(np.tile(kit["lons"].astype("float64"), kit["lats"].size))[kit["masque"]]
    touches = {}
    for nom, delta in deltas.items():
        dedans = np.zeros(etat.size, dtype=bool)
        for lon0, lon1, lat0, lat1 in BOITES_SCENARIO[nom]:
            dedans |= (lons >= lon0) & (lons <= lon1) & (lats >= lat0) & (lats <= lat1)
        etat[dedans] += float(delta)
        touches[nom] = int(dedans.sum())
    return etat, touches


def projeter(kit, etat):
    """Probabilite experimentale, ressemblances et analogues d'un etat."""
    annee = int(kit["annee"])
    w = kit["w"].astype("float64")
    d = etat - kit["pente"].astype("float64") * (annee - float(kit["ybar"]))
    r_rec = _correlation(kit["centroides"].astype("float64"), d, w)
    logit = float(kit["intercept"]) + float(kit["coef"] @ r_rec)
    r_mem = _correlation(kit["centroides_memoire"].astype("float64"), d, w)
    r_ana = _correlation(kit["etats_candidats"].astype("float64"), d, w)
    ordre = np.argsort(-r_ana)
    sortie = {
        "probabilite_experimentale": 1 / (1 + np.exp(-logit)),
        "ressemblance_memoire": {int(k): float(r_mem[k]) for k in range(r_mem.size)},
        "analogues": [(int(kit["annees_candidates"][i]), float(r_ana[i])) for i in ordre[:5]],
    }
    prep = familles.depuis_kit(kit)
    if prep is not None:  # kit produit avant le 08/10/2026: pas de familles
        sortie["familles_extremes"] = familles.evaluer(prep, etat, annee, w)
    return sortie


# =============================================================================
# Trajectoire mensuelle
# =============================================================================
def trajectoire(ctx, modele, annee, centroides_memoire):
    """Projection des etats cumules: novembre, novembre-decembre, ... avril.

    Montre comment la lecture de l'ocean evolue pendant la veille. Le modele
    est calibre sur des moyennes de SIX mois: les premiers points, plus
    bruites, sont indicatifs.
    """
    mois = [m for m in ctx.cube.mois_etat(annee) if ctx.cube.a_le_mois(*m)]
    points = []
    cumul = []
    for a, m in mois:
        cumul.append(ctx.cube.mensuel(a, m).reshape(-1)[ctx.masque].astype("float64"))
        champ = np.mean(cumul, axis=0)
        cfg = modele.configs
        r = _correlation(centroides_memoire, cfg.detrend(champ, annee), ctx.w)
        k = int(np.argmax(r))
        points.append({"jusqu_a": "%d-%02d" % (a, m), "n_mois": len(cumul),
                       "probabilite_experimentale": round(modele.probabilite(champ, annee), 3),
                       "configuration": k, "correlation": round(float(r[k]), 3)})
    return points
