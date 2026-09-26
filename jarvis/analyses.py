"""Moteur de recalcul des teleconnexions, pour les outils a la demande.

get_teleconnection lit les correlations DEJA calculees par le script 04.
Ce module les RECALCULE, avec les fonctions memes du script 04 (import du
fichier, pas de copie): agregation annuelle par phase, detrend lineaire,
Pearson + Spearman, correction n_eff AR1. Un recalcul sur la periode entiere
redonne donc au dix-millieme les valeurs des CSV (verifie par les tests), et
un recalcul modifie (annees exclues, sous-periode) ne differe que par ce que
l'utilisateur a change.

Le modele ne fournit que des PARAMETRES (indice, phase, lag, annees): aucun
code du modele n'est execute. C'est ce qui rend ces calculs surs en profil
public.

Deux usages:
  - correlation(): une correlation recalculee sur un sous-ensemble d'annees;
  - analogues(): les annees dont l'etat oceanique avant la phase ressemble le
    plus a celui d'une annee de reference, et ce qu'elles ont donne.
"""
import contextlib
import importlib.util
import io
import math
import threading

from .config import PROJECT_DIR

ANNEE_MIN, ANNEE_MAX = 1983, 2023
MIN_ANNEES = 10

_verrou = threading.Lock()
_etat = {}


class AnalyseIndisponible(Exception):
    """Fichiers du script 04 ou donnees d'entree absents."""


def _script04():
    """Le module du script 04, importe une fois (son nom commence par un
    chiffre: importlib, pas import)."""
    if "s04" not in _etat:
        chemin = PROJECT_DIR / "scripts" / "04_teleconnections_analysis.py"
        if not chemin.is_file():
            raise AnalyseIndisponible("Script 04 introuvable: %s" % chemin)
        spec = importlib.util.spec_from_file_location("jarvis_script04", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _etat["s04"] = module
    return _etat["s04"]


def donnees():
    """(script04, evenements mensuels, indices mensuels), charges une fois.

    Les loaders du script 04 impriment leur progression: on la fait taire,
    elle n'a rien a faire dans les journaux du service.
    """
    with _verrou:
        if "donnees" not in _etat:
            s04 = _script04()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ev = s04.load_events_monthly(s04.EVENTS_FILE)
                    ind = s04.load_indices_monthly(s04.INDICES_FILE)
            except (OSError, ValueError, KeyError) as exc:
                raise AnalyseIndisponible(str(exc))
            _etat["donnees"] = (s04, ev, ind)
        return _etat["donnees"]


def mois_de_phase(phase):
    s04 = _script04()
    if phase in s04.PHASE_MONTHS:
        return list(s04.PHASE_MONTHS[phase])
    # "Toutes phases": union des mois de saison, comme run() du script 04.
    return sorted({m for mois in s04.PHASE_MONTHS.values() for m in mois})


def _fini(v, decimales=4):
    if v is None:
        return None
    v = float(v)
    return round(v, decimales) if math.isfinite(v) else None


def serie_annuelle(phase, lag, indice, metrique):
    """DataFrame (year, metrique, indice) AVANT detrend, 1983-2023.

    En cache: le test de sensibilite annee par annee la redemande 41 fois,
    et merge_annual_lag coute ~80 ms."""
    cle = ("serie", phase, int(lag), indice, metrique)
    with _verrou:
        if cle in _etat:
            return _etat[cle].copy()
    s04, ev, ind = donnees()
    fusion = s04.merge_annual_lag(ev, ind, mois_de_phase(phase), int(lag), [indice])
    serie = fusion[["year", metrique, indice]].copy()
    with _verrou:
        _etat[cle] = serie
    return serie.copy()


def correlation(phase, lag, indice, metrique, annees=None):
    """Correlation recalculee sur les annees donnees (toutes par defaut).

    Le detrend est applique sur les annees RETENUES: retirer une annee
    change aussi la tendance estimee, exactement comme si le script 04 avait
    tourne sans elle.
    """
    from scipy.stats import pearsonr, spearmanr

    s04, _, _ = donnees()
    serie = serie_annuelle(phase, lag, indice, metrique)
    if annees is not None:
        serie = serie[serie["year"].isin(set(annees))]
    serie = s04.detrend_columns(serie, [indice])
    if metrique != "n_events":
        serie = s04.detrend_columns(serie, [metrique])
    paire = serie[["year", metrique, indice]].dropna()
    n = int(len(paire))
    if n < MIN_ANNEES:
        return {"n": n, "calculable": False,
                "raison": "moins de %d annees exploitables" % MIN_ANNEES}
    x = paire[metrique].values.astype(float)
    y = paire[indice].values.astype(float)
    pr, pp = pearsonr(x, y)
    sr, sp = spearmanr(x, y)
    n_eff = s04.compute_n_eff(x, y)
    return {
        "calculable": True,
        "n": n,
        "n_eff": int(n_eff),
        "annees": [int(a) for a in paire["year"]],
        "pearson_r": _fini(pr),
        "pearson_p": _fini(pp),
        "pearson_p_neff": _fini(s04.p_from_r_neff(pr, n_eff)),
        "spearman_r": _fini(sr),
        "spearman_p_neff": _fini(s04.p_from_r_neff(sr, n_eff)),
        # Pour la figure: les points de la correlation, apres detrend.
        "points": [(int(a), _fini(xi, 3), _fini(yi, 3))
                   for a, xi, yi in zip(paire["year"], x, y)],
    }


def influence_annuelle(phase, lag, indice, metrique):
    """Correlation sans chaque annee a tour de role (jackknife).

    Repond a "ce resultat tient-il a une seule annee ?": si retirer 2020
    fait perdre la significativite, le signal repose sur 2020.
    """
    complete = correlation(phase, lag, indice, metrique)
    if not complete.get("calculable"):
        return complete, []
    effets = []
    for annee in complete["annees"]:
        autres = [a for a in complete["annees"] if a != annee]
        r = correlation(phase, lag, indice, metrique, autres)
        if r.get("calculable"):
            effets.append({"annee_retiree": annee, "pearson_r": r["pearson_r"],
                           "p_neff": r["pearson_p_neff"],
                           "ecart_r": _fini(r["pearson_r"] - complete["pearson_r"], 4)})
    effets.sort(key=lambda e: -abs(e["ecart_r"] or 0))
    return complete, effets


# =============================================================================
# Annees analogues
# =============================================================================
def etat_oceanique(phase, indices, mois_avant=3):
    """Moyenne des indices sur les `mois_avant` mois qui precedent la phase.

    Pour la pleine saison (juillet-aout) et mois_avant=3: avril, mai, juin.
    C'est la fenetre des lags 1 a 3, que l'on connait AVANT la saison: une
    analogie construite dessus peut servir a anticiper, pas seulement a
    decrire apres coup.
    """
    cle = ("etat", phase, tuple(indices), int(mois_avant))
    with _verrou:
        if cle in _etat:
            return _etat[cle].copy()
    import pandas as pd

    _, _, ind = donnees()
    par_mois = ind.set_index(["year", "month"])[list(indices)]
    debut = mois_de_phase(phase)[0]
    lignes = {}
    for annee in range(ANNEE_MIN, ANNEE_MAX + 1):
        cibles = []
        for k in range(1, mois_avant + 1):
            mois, an = debut - k, annee
            while mois <= 0:
                mois += 12
                an -= 1
            cibles.append((an, mois))
        # Moyenne des mois disponibles (NaN ignores), comme merge_annual_lag.
        lignes[annee] = par_mois.reindex(cibles).mean(axis=0, skipna=True)
    etat = pd.DataFrame(lignes).T
    etat.index.name = "year"
    with _verrou:
        _etat[cle] = etat
    return etat.copy()


def resultats_de_phase(phase):
    """Metriques annuelles de la phase (sans detrend): ce qu'a donne la saison."""
    s04, ev, ind = donnees()
    fusion = s04.merge_annual_lag(ev, ind, mois_de_phase(phase), 0, [])
    return fusion.set_index("year")


def analogues(phase, annee_ref, indices, nombre=5, mois_avant=3,
              metrique="max_precip"):
    """Les `nombre` annees les plus proches de annee_ref, et leur bilan.

    Distance euclidienne sur les indices standardises (z-score 1983-2023):
    sans standardisation, un indice de forte variance (Nino12) ecraserait
    les autres. L'annee de reference est exclue de ses propres analogues.
    """
    import numpy as np

    etat = etat_oceanique(phase, indices, mois_avant).dropna()
    if annee_ref not in etat.index:
        raise AnalyseIndisponible("Etat oceanique indisponible pour %d." % annee_ref)
    z = (etat - etat.mean()) / etat.std(ddof=0).replace(0, np.nan)
    z = z.dropna(axis=1)
    ref = z.loc[annee_ref]
    distances = np.sqrt(((z - ref) ** 2).sum(axis=1)).drop(annee_ref)
    proches = distances.sort_values().head(nombre)

    bilan = resultats_de_phase(phase)
    serie = bilan[metrique]
    moyenne = float(serie.mean())

    def rang_pct(v):
        if v is None or not np.isfinite(v):
            return None
        return _fini(100.0 * float((serie.dropna() < v).mean()), 1)

    liste = []
    for annee, d in proches.items():
        v = serie.get(annee)
        v = None if v is None or not np.isfinite(v) else float(v)
        liste.append({
            "annee": int(annee),
            "distance": _fini(d, 3),
            "etat_standardise": {k: _fini(z.loc[annee, k], 2) for k in z.columns},
            metrique: _fini(v, 2),
            "n_events": int(bilan.loc[annee, "n_events"]),
            "rang_percentile": rang_pct(v),
        })
    valeurs = [a[metrique] for a in liste if a[metrique] is not None]
    composite = float(np.mean(valeurs)) if valeurs else None
    reel = serie.get(annee_ref)
    reel = None if reel is None or not np.isfinite(reel) else float(reel)
    return {
        "etat_reference": {k: _fini(ref[k], 2) for k in z.columns},
        "analogues": liste,
        "composite": _fini(composite, 2),
        "moyenne_1983_2023": _fini(moyenne, 2),
        "valeur_reelle_annee_ref": _fini(reel, 2),
        "n_events_annee_ref": int(bilan.loc[annee_ref, "n_events"])
        if annee_ref in bilan.index else None,
    }


def competence_analogues(phase, indices, nombre=5, mois_avant=3,
                         metrique="max_precip"):
    """La methode des analogues a-t-elle un pouvoir predictif ?

    Validation croisee "leave-one-out": chaque annee est "prevue" par la
    moyenne de ses analogues (elle-meme exclue), puis on correle prevision
    et realite. Sans ce chiffre, une liste d'analogues ressemble a une
    prevision alors qu'elle peut ne rien valoir.
    """
    import numpy as np
    from scipy.stats import pearsonr

    s04, _, _ = donnees()
    etat = etat_oceanique(phase, indices, mois_avant).dropna()
    bilan = resultats_de_phase(phase)[metrique]
    prevu, observe = [], []
    for annee in etat.index:
        r = analogues(phase, int(annee), indices, nombre, mois_avant, metrique)
        v = bilan.get(annee)
        if r["composite"] is None or v is None or not np.isfinite(v):
            continue
        prevu.append(r["composite"])
        observe.append(float(v))
    if len(prevu) < MIN_ANNEES:
        return {"calculable": False}
    x, y = np.array(prevu), np.array(observe)
    r, _ = pearsonr(x, y)
    n_eff = s04.compute_n_eff(x, y)
    return {"calculable": True, "n": len(prevu), "r_prevu_observe": _fini(r, 3),
            "p_neff": _fini(s04.p_from_r_neff(r, n_eff), 4)}
