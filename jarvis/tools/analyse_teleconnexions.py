"""Outil analyze_teleconnections: lecture critique des correlations (Phase 7).

get_teleconnection dit QUELLES correlations existent; cet outil dit ce qu'elles
VALENT. Il relit les memes CSV (load_telecon, sortie du script 04) et repond a
trois questions que l'on pose toujours a un tableau de 330 correlations:

  bilan_significativite  y a-t-il plus de correlations significatives que le
                         hasard n'en produirait ? Le script 04 ne corrige pas
                         les comparaisons multiples (FDR retire): sur 330
                         tests a 5 %, environ 16 ressortent par pur hasard.
                         Sans ce rappel, chaque etoile se lit comme un signal.
  comparer_phases        un meme indice agit-il en debut, en pleine et en fin
                         de saison ? Meilleur lag et signe, phase par phase.
  robustesse             une correlation significative tient-elle quand on
                         change de coefficient (Spearman), quand on corrige
                         l'autocorrelation (AR1), et aux lags voisins ?
"""
from scipy import stats

from .common import (INDICES, METRIQUES, PHASES, PHASES_LABELS, PHASES_TOUTES,
                     SOURCE_CORRELATIONS, ToolInputError, arrondir, champ_entier,
                     champ_enum, etoiles, resoudre_indice, resoudre_phase)

NAME = "analyze_teleconnections"
LABEL = "Analyse critique des téléconnexions"
PERMISSION = "public"
DATASETS = ("correlations",)

ANALYSES = ["bilan_significativite", "comparer_phases", "robustesse"]

BASSINS = {
    "Pacifique (ENSO)": ["Nino12", "Nino3", "Nino34", "Nino4"],
    "Ocean Indien": ["IOD", "IOBM"],
    "Atlantique": ["TNA", "TSA", "ATL3", "AMM", "AMO"],
}

SEUIL = 0.05
SEUIL_VOISIN = 0.10
LIMITE_MAX = 15

DESCRIPTION = (
    "Analyse critique des correlations indices SST / pluies extremes. "
    "analysis=bilan_significativite: combien de correlations significatives "
    "par phase et par bassin oceanique, comparees au nombre attendu par pur "
    "hasard (test binomial) -- a utiliser des qu'on demande si les resultats "
    "sont solides, ou quel ocean domine. analysis=comparer_phases: pour un "
    "indice, meilleur lag et signe en debut, pleine et fin de saison. "
    "analysis=robustesse: pour une phase, note chaque correlation "
    "significative selon trois criteres (p corrigee AR1, confirmation par "
    "Spearman, coherence des lags voisins) et distingue les signaux robustes "
    "des signaux fragiles. Complementaire de get_teleconnection, qui liste "
    "les valeurs brutes."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string", "enum": ANALYSES,
                     "description": "Type d'analyse."},
        "phase": {"type": "string", "enum": PHASES_TOUTES,
                  "description": "Phase de saison. Requise pour robustesse; "
                                 "pour bilan_significativite, omettre pour "
                                 "comparer les trois phases."},
        "index": {"type": "string", "enum": INDICES,
                  "description": "Indice SST. Requis pour comparer_phases; "
                                 "filtre optionnel pour robustesse."},
        "metric": {"type": "string", "enum": sorted(METRIQUES),
                   "description": "Metrique de pluie. Defaut: max_precip."},
        "limit": {"type": "integer",
                  "description": "robustesse: nombre de correlations "
                                 "detaillees (1 a 15, defaut 8)."},
    },
    "required": ["analysis"],
}

AVERTISSEMENT = ("correlation != causalite; p_neff corrigee AR1; pas de "
                 "correction FDR dans le script 04")


def _bassin(indice):
    for nom, membres in BASSINS.items():
        if indice in membres:
            return nom
    return "Autre"


def _phase_ou_erreur(data, phase):
    if phase not in data["correlations"]:
        raise ToolInputError(
            "Aucun resultat de correlation pour la phase %s. Phases "
            "disponibles: %s." % (phase, ", ".join(sorted(data["correlations"]))))
    return data["correlations"][phase]


def _meilleure(df):
    ligne = df.loc[df["pearson_r"].abs().idxmax()]
    return {
        "indice": ligne["index"],
        "lag_mois": int(ligne["lag_months"]),
        "pearson_r": arrondir(ligne["pearson_r"], 3),
        "p_neff": arrondir(ligne["pearson_p_neff"], 4),
        "significativite": etoiles(ligne["pearson_p_neff"]) or "non significatif",
    }


# --- bilan_significativite ---------------------------------------------------
def _bilan_phase(df):
    n = int(len(df))
    k = int((df["pearson_p_neff"] < SEUIL).sum())
    k_nominal = int((df["pearson_p"] < SEUIL).sum()) if "pearson_p" in df else None
    attendus = n * SEUIL
    # P(X >= k) sous l'hypothese nulle: aucune vraie correlation, chaque test
    # a 5 % de chances de sortir significatif.
    p_binom = float(stats.binom.sf(k - 1, n, SEUIL)) if n else None

    if k <= attendus:
        verdict = ("pas plus de correlations significatives que le hasard "
                   "n'en produirait")
    elif p_binom is not None and p_binom < SEUIL:
        verdict = "nettement plus de correlations significatives que le hasard"
    else:
        verdict = ("un peu plus que le hasard, mais l'ecart n'est pas "
                   "concluant a lui seul")

    bassins = []
    for nom, membres in BASSINS.items():
        sous = df[df["index"].isin(membres)]
        if sous.empty:
            continue
        bassins.append({
            "bassin": nom,
            "n_tests": int(len(sous)),
            "n_significatives": int((sous["pearson_p_neff"] < SEUIL).sum()),
            "attendues_par_hasard": arrondir(len(sous) * SEUIL, 1),
            "correlation_la_plus_forte": _meilleure(sous),
        })
    return {
        "n_tests": n,
        "n_significatives_ar1": k,
        "n_significatives_nominales": k_nominal,
        "attendues_par_hasard": arrondir(attendus, 1),
        "p_binomiale": arrondir(p_binom, 4),
        "verdict": verdict,
        "par_bassin": bassins,
    }


def _bilan(params, data, metrique):
    if params.get("phase"):
        phases = [resoudre_phase(params["phase"])]
        _phase_ou_erreur(data, phases[0])
    else:
        phases = [p for p in PHASES if p in data["correlations"]]
    resultats = []
    for phase in phases:
        df = data["correlations"][phase]
        df = df[df["metric"] == metrique]
        if df.empty:
            continue
        bloc = _bilan_phase(df)
        bloc["phase"] = phase
        bloc["phase_label"] = PHASES_LABELS.get(phase, phase)
        resultats.append(bloc)
    return {
        "analyse": "bilan_significativite",
        "metrique": metrique,
        "seuil": SEUIL,
        "phases": resultats,
        "lecture": ("attendues_par_hasard = n_tests x 5 %. p_binomiale = "
                    "probabilite d'observer au moins autant de correlations "
                    "significatives s'il n'y avait aucun lien reel."),
        "limite": ("Les tests ne sont pas independants (lags voisins, indices "
                   "lies comme AMM = TNA - TSA): le test binomial est donc "
                   "optimiste, un 'nettement plus' reste a confirmer."),
        "avertissement": AVERTISSEMENT,
        "source": SOURCE_CORRELATIONS,
    }


# --- comparer_phases ---------------------------------------------------------
def _comparer(params, data, metrique):
    if not params.get("index"):
        raise ToolInputError("Le parametre index est requis pour "
                             "comparer_phases. Valeurs acceptees: %s."
                             % ", ".join(INDICES))
    indice = resoudre_indice(params["index"])
    lignes = []
    for phase in PHASES_TOUTES:
        if phase not in data["correlations"]:
            continue
        df = data["correlations"][phase]
        sous = df[(df["metric"] == metrique) & (df["index"] == indice)]
        if sous.empty:
            continue
        meilleure = _meilleure(sous)
        meilleure.pop("indice")
        lignes.append({
            "phase": phase,
            "phase_label": PHASES_LABELS.get(phase, phase),
            "meilleur_lag": meilleure,
            "n_lags_significatifs": int((sous["pearson_p_neff"] < SEUIL).sum()),
            "n_lags": int(len(sous)),
        })
    if not lignes:
        return {"analyse": "comparer_phases", "indice": indice,
                "metrique": metrique, "phases": [],
                "message": "Aucune correlation pour cet indice et cette metrique.",
                "source": SOURCE_CORRELATIONS}

    signes = {("+" if l["meilleur_lag"]["pearson_r"] > 0 else "-")
              for l in lignes if l["phase"] in PHASES
              and l["meilleur_lag"]["significativite"] != "non significatif"}
    return {
        "analyse": "comparer_phases",
        "indice": indice,
        "bassin": _bassin(indice),
        "metrique": metrique,
        "phases": lignes,
        "signe_stable_entre_phases_significatives": (len(signes) <= 1
                                                     if signes else None),
        "avertissement": AVERTISSEMENT,
        "source": SOURCE_CORRELATIONS,
    }


# --- robustesse ----------------------------------------------------------------
def _voisins_coherents(df, indice, lag, signe):
    """Un lag voisin (lag-1 ou lag+1) du meme signe, au moins a p_neff < 0.10.

    Un vrai signal oceanique varie lentement: une correlation isolee a un seul
    lag, entouree de zeros, ressemble davantage a un accident d'echantillon.
    """
    voisins = df[(df["index"] == indice)
                 & (df["lag_months"].isin([lag - 1, lag + 1]))]
    for _, v in voisins.iterrows():
        if (v["pearson_r"] > 0) == signe and v["pearson_p_neff"] < SEUIL_VOISIN:
            return True
    return False


def _robustesse(params, data, metrique):
    if not params.get("phase"):
        raise ToolInputError("Le parametre phase est requis pour robustesse. "
                             "Valeurs acceptees: %s." % ", ".join(PHASES_TOUTES))
    phase = resoudre_phase(params["phase"])
    df = _phase_ou_erreur(data, phase)
    df = df[df["metric"] == metrique]
    indice = resoudre_indice(params["index"]) if params.get("index") else None
    limite = champ_entier(params, "limit", mini=1, maxi=LIMITE_MAX, defaut=8)

    candidates = df[(df["pearson_p_neff"] < SEUIL) | (df["pearson_p"] < SEUIL)]
    if indice is not None:
        candidates = candidates[candidates["index"] == indice]

    notes = []
    for _, ligne in candidates.iterrows():
        signe = ligne["pearson_r"] > 0
        ar1 = bool(ligne["pearson_p_neff"] < SEUIL)
        spearman = bool(ligne["spearman_p_neff"] < SEUIL
                        and (ligne["spearman_r"] > 0) == signe)
        voisins = _voisins_coherents(df, ligne["index"],
                                     int(ligne["lag_months"]), signe)
        score = int(ar1) + int(spearman) + int(voisins)
        if score == 3:
            verdict = "robuste"
        elif score == 2 and ar1:
            verdict = "moderee"
        else:
            verdict = "fragile"
        notes.append({
            "indice": ligne["index"],
            "lag_mois": int(ligne["lag_months"]),
            "pearson_r": arrondir(ligne["pearson_r"], 3),
            "p_nominale": arrondir(ligne["pearson_p"], 4),
            "p_neff": arrondir(ligne["pearson_p_neff"], 4),
            "criteres": {
                "significative_apres_AR1": ar1,
                "confirmee_par_spearman": spearman,
                "lags_voisins_coherents": voisins,
            },
            "score_sur_3": score,
            "verdict": verdict,
        })

    notes.sort(key=lambda n: (-n["score_sur_3"], -abs(n["pearson_r"] or 0)))
    compte = {v: sum(1 for n in notes if n["verdict"] == v)
              for v in ("robuste", "moderee", "fragile")}
    nominales_seules = sum(1 for n in notes
                           if not n["criteres"]["significative_apres_AR1"])
    return {
        "analyse": "robustesse",
        "phase": phase,
        "phase_label": PHASES_LABELS.get(phase, phase),
        "metrique": metrique,
        "filtre_indice": indice,
        "n_candidates": len(notes),
        "repartition": compte,
        "significatives_seulement_sans_correction_AR1": nominales_seules,
        "correlations": notes[:limite],
        "lecture": ("robuste = les trois criteres; moderee = AR1 + un autre; "
                    "fragile = un seul critere, ou significative seulement "
                    "avant correction AR1."),
        "avertissement": AVERTISSEMENT,
        "source": SOURCE_CORRELATIONS,
    }


def run(params, data):
    analyse = champ_enum(params, "analysis", ANALYSES)
    if analyse is None:
        raise ToolInputError("Le parametre analysis est requis. Valeurs "
                             "acceptees: %s." % ", ".join(ANALYSES))
    metrique = champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")
    if analyse == "bilan_significativite":
        return _bilan(params, data, metrique)
    if analyse == "comparer_phases":
        return _comparer(params, data, metrique)
    return _robustesse(params, data, metrique)
