"""Prevision saisonniere officielle Copernicus C3S, traduite en risque d'annee extreme.

Source: jeu CDS "seasonal-monthly-single-levels", precipitation totale
(moyennes mensuelles de chaque membre), prevision emise en AVRIL, mois
juillet-aout-septembre (echeances 4, 5, 6), boite Senegal 12-17 N, 18-11 W.

Traduction en trois temps:
  1. ANOMALIE: pluie JAS moyenne d'ensemble standardisee par la climatologie
     des retro-previsions du meme systeme (z-score).
  2. CALIBRATION: regression logistique de "annee extreme CHIRPS" (veille.
     annees) sur ce z-score, sur les annees de retro-prevision communes
     avec CHIRPS (SEAS5: 1981-2016, 36 annees).
  3. COMPETENCE: la meme calibration evaluee en LOYO (AUC, test par
     permutation, Brier skill score). Elle fixe la confiance du bulletin.

Aussi rapporte tel quel: la part des membres au-dessus du tercile superieur
climatologique (probabilite "saison plus humide que la normale" du modele).

Acces: compte gratuit CDS, cle dans .env (CDSAPI_KEY) ou ~/.cdsapirc, et
licence "seasonal forecast" acceptee sur le site. Les fichiers telecharges
sont gardes dans data/raw/c3s/ (un fichier par annee d'emission): une
retro-prevision ne se telecharge qu'une fois.
"""
import os
import warnings

import numpy as np

from . import RACINE
from . import annees as mod_annees

DOSSIER = RACINE / "data" / "raw" / "c3s"
JEU = "seasonal-monthly-single-levels"
URL_CDS = "https://cds.climate.copernicus.eu/api"
BOITE = [17, -18, 12, -11]          # N, O, S, E (convention CDS)
MOIS_EMISSION = 4                   # avril
ECHEANCES = (4, 5, 6)               # emission avril -> juillet, aout, septembre

SYSTEMES = {
    # centre: (systeme, annees de retro-prevision)
    "ecmwf": ("51", range(1981, 2017)),
}
SYSTEME_DEFAUT = "ecmwf"


class C3SIndisponible(Exception):
    """Cle absente, telechargement impossible ou fichier illisible."""


# =============================================================================
# Acces CDS
# =============================================================================
def charger_env(chemin=RACINE / ".env"):
    """Lit CDSAPI_KEY / CDSAPI_URL du .env du projet (et rien d'autre).

    Le .env porte aussi les secrets de Jarvis: on n'en importe que les deux
    variables CDS, sans ecraser une valeur deja presente dans l'environnement.
    """
    if not chemin.is_file():
        return
    for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        nom, sep, valeur = ligne.strip().partition("=")
        if sep and nom.strip() in ("CDSAPI_KEY", "CDSAPI_URL") and valeur.strip():
            os.environ.setdefault(nom.strip(), valeur.strip().strip('"').strip("'"))


def cle_configuree():
    charger_env()
    if os.environ.get("CDSAPI_KEY"):
        return True
    return os.path.isfile(os.path.join(os.path.expanduser("~"), ".cdsapirc"))


def _client():
    try:
        import cdsapi
    except ImportError:
        raise C3SIndisponible("Module cdsapi absent: py -3 -m pip install cdsapi")
    charger_env()
    cle = os.environ.get("CDSAPI_KEY")
    try:
        if cle:
            return cdsapi.Client(url=os.environ.get("CDSAPI_URL", URL_CDS), key=cle,
                                 quiet=True, progress=False)
        return cdsapi.Client(quiet=True, progress=False)
    except Exception as exc:  # cdsapi leve une Exception nue si rien n'est configure
        raise C3SIndisponible("Cle Copernicus CDS non configuree (%s). Ajouter CDSAPI_KEY "
                              "dans .env." % exc)


def requete(annee, centre=SYSTEME_DEFAUT, mois=MOIS_EMISSION):
    systeme, _ = SYSTEMES[centre]
    return {
        "originating_centre": centre,
        "system": systeme,
        "variable": ["total_precipitation"],
        "product_type": ["monthly_mean"],
        "year": [str(annee)],
        "month": ["%02d" % mois],
        "leadtime_month": [str(e) for e in ECHEANCES],
        "data_format": "netcdf",
        "area": BOITE,
    }


def fichier(annee, centre=SYSTEME_DEFAUT, mois=MOIS_EMISSION):
    systeme, _ = SYSTEMES[centre]
    return DOSSIER / ("%s_s%s_%d_emis%02d.nc" % (centre, systeme, annee, mois))


def telecharger(annee, centre=SYSTEME_DEFAUT, mois=MOIS_EMISSION, journal=print):
    """Telecharge (si absent) la prevision emise en `mois` de `annee`."""
    chemin = fichier(annee, centre, mois)
    if chemin.is_file() and chemin.stat().st_size > 0:
        return chemin
    DOSSIER.mkdir(parents=True, exist_ok=True)
    client = _client()
    temporaire = chemin.with_suffix(".part")
    journal("  C3S %s: telechargement %d (emission %02d)..." % (centre, annee, mois))
    try:
        client.retrieve(JEU, requete(annee, centre, mois), str(temporaire))
    except Exception as exc:
        if temporaire.exists():
            temporaire.unlink()
        raise C3SIndisponible("Telechargement C3S %d impossible: %s" % (annee, exc))
    temporaire.replace(chemin)
    return chemin


# =============================================================================
# Lecture
# =============================================================================
_NOMS_MEMBRE = ("number", "realization", "member", "ensemble")
_NOMS_ECHEANCE = ("forecastMonth", "leadtime_month", "forecast_period", "step")


def lire(chemin):
    """Pluie JAS (mm/jour) de chaque membre, moyennee sur la boite: vecteur (membres,)."""
    import xarray as xr

    from .cube import _chemin_court
    try:
        ds = xr.open_dataset(_chemin_court(chemin))
    except Exception as exc:
        raise C3SIndisponible("Fichier C3S illisible (%s): %s" % (chemin.name, exc))
    try:
        return pluie_membres(ds)
    finally:
        ds.close()


def pluie_membres(ds):
    noms = [v for v in ds.data_vars if v in ("tprate", "tp")] or list(ds.data_vars)
    if not noms:
        raise C3SIndisponible("Aucune variable de precipitation dans le fichier C3S.")
    da = ds[noms[0]]
    lat = next((d for d in da.dims if d.startswith("lat")), None)
    lon = next((d for d in da.dims if d.startswith("lon")), None)
    membre = next((d for d in da.dims if d in _NOMS_MEMBRE), None)
    if lat is None or lon is None or membre is None:
        raise C3SIndisponible("Dimensions C3S inattendues: %s" % (da.dims,))
    poids = np.cos(np.deg2rad(da[lat]))
    boite = da.weighted(poids).mean(dim=[lat, lon])
    autres = [d for d in boite.dims if d != membre]
    valeurs = boite.mean(dim=autres).values.astype("float64")
    # tprate en m/s -> mm/jour; tp (cumul) laisse tel quel, seul le z-score compte.
    if noms[0] == "tprate":
        valeurs = valeurs * 86400.0 * 1000.0
    valeurs = valeurs[np.isfinite(valeurs)]
    if valeurs.size == 0:
        raise C3SIndisponible("Prevision C3S vide.")
    return valeurs


# =============================================================================
# Calibration et prevision
# =============================================================================
def calibrer(membres_par_annee, empreinte=None):
    """Calibration CHIRPS de la pluie JAS C3S, et sa competence LOYO.

    membres_par_annee: {annee: vecteur des membres} pour les retro-previsions.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    empreinte = mod_annees.empreinte() if empreinte is None else empreinte
    annees = sorted(a for a in membres_par_annee if a in empreinte.index)
    if len(annees) < 15:
        raise C3SIndisponible("Trop peu d'annees de retro-prevision communes avec CHIRPS (%d)."
                              % len(annees))
    moyennes = np.array([np.mean(membres_par_annee[a]) for a in annees])
    tous = np.concatenate([membres_par_annee[a] for a in annees])
    clim_moy, clim_ec = float(moyennes.mean()), float(moyennes.std(ddof=1))
    tercile_sup = float(np.quantile(tous, 2 / 3))
    z = (moyennes - clim_moy) / clim_ec
    s = mod_annees.seuil(empreinte, annees)
    y = np.array([int(empreinte.loc[a] > s) for a in annees])

    # Competence LOYO: tout est reestime sans l'annee testee (seuil compris).
    prevu, observe, base = [], [], []
    for i, a in enumerate(annees):
        autres = [j for j in range(len(annees)) if j != i]
        m, e = moyennes[autres].mean(), moyennes[autres].std(ddof=1)
        s_i = mod_annees.seuil(empreinte, [annees[j] for j in autres])
        y_i = np.array([int(empreinte.loc[annees[j]] > s_i) for j in autres])
        if y_i.min() == y_i.max():
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lr = LogisticRegression(C=1.0).fit(((moyennes[autres] - m) / e)[:, None], y_i)
        prevu.append(float(lr.predict_proba([[(moyennes[i] - m) / e]])[0, 1]))
        observe.append(int(empreinte.loc[a] > s_i))
        base.append(float(y_i.mean()))
    P, O, B = map(np.array, (prevu, observe, base))
    rng = np.random.default_rng(0)
    auc = float(roc_auc_score(O, P))
    perm = np.array([roc_auc_score(rng.permutation(O), P) for _ in range(2000)])
    competence = {
        "n": int(len(O)), "annees_extremes": int(O.sum()),
        "auc": round(auc, 3), "p_permutation": round(float((perm >= auc).mean()), 4),
        "brier_skill_score": round(float(1 - np.mean((P - O) ** 2) / np.mean((B - O) ** 2)), 3),
        "correlation_pluie_empreinte": round(float(np.corrcoef(
            moyennes, [empreinte.loc[a] for a in annees])[0, 1]), 3),
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lr = LogisticRegression(C=1.0).fit(z[:, None], y)
    return {
        "annees": [int(a) for a in annees],
        "climatologie_mm_jour": round(clim_moy, 3), "ecart_type_mm_jour": round(clim_ec, 3),
        "tercile_superieur_mm_jour": round(tercile_sup, 3),
        "coefficient": float(lr.coef_[0, 0]), "intercept": float(lr.intercept_[0]),
        "seuil_empreinte": round(s, 1), "base": round(float(y.mean()), 3),
        "competence": competence,
    }


def prevoir(membres, calibration):
    """Probabilite d'annee extreme pour une prevision (vecteur des membres)."""
    moyenne = float(np.mean(membres))
    z = (moyenne - calibration["climatologie_mm_jour"]) / calibration["ecart_type_mm_jour"]
    logit = calibration["intercept"] + calibration["coefficient"] * z
    return {
        "pluie_jas_mm_jour": round(moyenne, 3),
        "anomalie_standardisee": round(z, 2),
        "part_membres_au_dessus_normale": round(float(np.mean(
            membres > calibration["tercile_superieur_mm_jour"])), 3),
        "n_membres": int(len(membres)),
        "probabilite_annee_extreme": round(float(1 / (1 + np.exp(-logit))), 3),
    }


def calibration_complete(centre=SYSTEME_DEFAUT, journal=print):
    """Telecharge les retro-previsions manquantes puis calibre."""
    _, annees = SYSTEMES[centre]
    membres = {}
    for a in annees:
        membres[a] = lire(telecharger(a, centre, journal=journal))
    cal = calibrer(membres)
    systeme, _ = SYSTEMES[centre]
    cal.update(centre=centre, systeme=systeme, emission="%02d" % MOIS_EMISSION,
               echeances=list(ECHEANCES), mois_cibles="juillet-aout-septembre")
    return cal


def prevision(annee, calibration, centre=SYSTEME_DEFAUT, journal=print):
    membres = lire(telecharger(annee, centre, journal=journal))
    return dict(prevoir(membres, calibration), centre=centre,
                systeme=SYSTEMES[centre][0], annee=int(annee), emission="%02d" % MOIS_EMISSION)
