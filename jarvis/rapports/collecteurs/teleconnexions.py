"""Rapport teleconnexions: correlations indices SST / pluies extremes.

Tout vient des sorties du script 04 (correlations_<phase>.csv) et des
analyses deja exposees par Iris (analyze_teleconnections: bilan face au
hasard, robustesse), plus la typologie K-Means (get_risk_cluster) et les 4
etats saisonniers (veille/etats.py). Ajout de ce module: l'intervalle de
confiance a 95 % de chaque correlation, par la transformation de Fisher sur
la taille d'echantillon effective (n_eff, AR1).

Garde-fou statistique: on ne met en avant que les correlations "robustes"
(significatives apres AR1, confirmees par Spearman, coherentes sur un
decalage voisin) et l'on rappelle combien de correlations le hasard seul
rendrait significatives.
"""
import json
import math

from ...config import PROJECT_DIR
from ...tools import analyse_teleconnexions as outil_ana
from ...tools import cartes as outil_cartes
from ...tools import clusters as outil_clusters
from ...tools import graphiques as outil_graph
from ...tools.common import PHASES
from .. import textes_fixes as tf
from ..document import Encadre
from ..faits import RegistreFaits, nombre_fr
from . import Collecte, CollecteImpossible, cellule, figure, fini, tableau

PERIODE = "1983-2023"
SRC = "CHIRPS v2 x NOAA OISST v2 (script 04)"
COURTS = {"Phase_1_debut": "p1", "Phase_2_pleine": "p2", "Phase_3_fin": "p3"}
LIBELLES = {"Phase_1_debut": "début de saison (mai-juin)",
            "Phase_2_pleine": "cœur de saison (juillet-août)",
            "Phase_3_fin": "fin de saison (septembre-octobre)"}
METRIQUES = {"max_precip": "l'intensité maximale des pluies extrêmes",
             "mean_precip": "l'intensité moyenne des pluies extrêmes",
             "max_anomaly": "l'anomalie maximale des pluies extrêmes",
             "coverage_percent": "l'étendue spatiale des pluies extrêmes",
             "n_events": "le nombre d'événements extrêmes"}
NOMS_INDICES = {
    "Nino12": "Niño 1+2, Pacifique est près des côtes sud-américaines",
    "Nino3": "Niño 3, Pacifique équatorial est",
    "Nino34": "Niño 3.4, indice de référence d'El Niño",
    "Nino4": "Niño 4, Pacifique équatorial ouest",
    "IOD": "dipôle de l'océan Indien",
    "IOBM": "mode de bassin de l'océan Indien",
    "TNA": "Atlantique tropical nord",
    "TSA": "Atlantique tropical sud",
    "ATL3": "Atlantique équatorial, langue d'eau froide",
    "AMM": "mode méridien atlantique, TNA moins TSA",
    "AMO": "oscillation multidécennale atlantique",
}
VERDICTS = {"robuste": "robuste", "moderee": "modérée", "fragile": "fragile"}
BILANS = {
    "pas plus de correlations significatives que le hasard n'en produirait":
        "pas plus que ce que le hasard produirait",
    "nettement plus de correlations significatives que le hasard":
        "nettement plus que ce que le hasard produirait",
    "un peu plus que le hasard, mais l'ecart n'est pas concluant a lui seul":
        "un peu plus que le hasard, sans que l'écart soit concluant à lui seul",
}
BASSINS = {"Pacifique (ENSO)": "le Pacifique (ENSO)", "Atlantique": "l'Atlantique",
           "Ocean Indien": "l'océan Indien", "Océan Indien": "l'océan Indien"}
# Sens d'une correlation negative ("quand l'indice est plus froid") par metrique.
SENS = {"max_precip": ("plus intenses", "moins intenses"),
        "mean_precip": ("plus intenses", "moins intenses"),
        "max_anomaly": ("plus marquées", "moins marquées"),
        "coverage_percent": ("plus étendues", "moins étendues"),
        "n_events": ("plus nombreuses", "moins nombreuses")}
ETATS = PROJECT_DIR / "outputs" / "clustering_saisonnier" / "etats_saisonniers.json"


def enumerer(elements):
    """['a', 'b', 'c'] -> 'a, b et c'."""
    elements = list(elements)
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]


def _p(phase, texte):
    """Gabarit d'une phase: PHASE -> libelle, {{fait:P_x}} -> {{fait:p2_x}}."""
    libelle = LIBELLES[phase][0].upper() + LIBELLES[phase][1:]
    return texte.replace("PHASE", libelle).replace("{{fait:P_", "{{fait:%s_" % COURTS[phase])


def ic_fisher(r, n_eff, niveau=1.96):
    """Intervalle de confiance a 95 % de r (transformation de Fisher, n_eff)."""
    r, n = fini(r), fini(n_eff)
    if r is None or n is None or n <= 3 or abs(r) >= 1:
        return None, None
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    return math.tanh(z - niveau * se), math.tanh(z + niveau * se)


def _ligne(df, indice, lag):
    sous = df[(df["index"] == indice) & (df["lag_months"] == lag)]
    return sous.iloc[0] if len(sous) else None


def _phase(c, data, phase, metrique):
    reg = c.registre
    k = COURTS[phase]
    df = data["correlations"].get(phase)
    if df is None:
        return None
    dfm = df[df["metric"] == metrique]
    if dfm.empty:
        return None
    bilan = outil_ana._bilan_phase(dfm)
    rob = outil_ana.run({"analysis": "robustesse", "phase": phase, "metric": metrique,
                         "limit": outil_ana.LIMITE_MAX}, data)
    reg.ajouter(k + "_n_tests", bilan["n_tests"], "corrélations testées (%s)" % LIBELLES[phase],
                "methode", SRC, PERIODE, format="entier")
    reg.ajouter(k + "_n_sig", bilan["n_significatives_ar1"],
                "corrélations significatives après correction AR1 (%s)" % LIBELLES[phase],
                "correle", SRC, PERIODE, format="entier")
    reg.ajouter(k + "_attendues", bilan["attendues_par_hasard"],
                "corrélations significatives attendues par hasard (%s)" % LIBELLES[phase],
                "methode", SRC, PERIODE, decimales=1)
    p_binom = bilan["p_binomiale"]
    if p_binom is not None:
        reg.ajouter(k + "_p_binom", "< 0,001" if p_binom < 0.001 else nombre_fr(p_binom, 3),
                    "probabilité d'autant de résultats significatifs sans lien réel (%s)"
                    % LIBELLES[phase], "methode", SRC, PERIODE, format="texte")
    reg.ajouter(k + "_verdict", BILANS.get(bilan["verdict"], bilan["verdict"]), "bilan face au hasard (%s)" % LIBELLES[phase],
                "correle", SRC, PERIODE, format="texte")
    rep = rob.get("repartition", {})
    reg.ajouter(k + "_n_robustes", rep.get("robuste", 0),
                "corrélations robustes (%s)" % LIBELLES[phase], "correle", SRC, PERIODE,
                format="entier")
    notes = [n for n in rob.get("correlations", []) if n["criteres"]["significative_apres_AR1"]]
    lignes_tab = []
    for n in notes[:8]:
        ligne = _ligne(dfm, n["indice"], n["lag_mois"])
        bas, haut = ic_fisher(ligne["pearson_r"], ligne["n_eff"]) if ligne is not None else (None, None)
        lignes_tab.append([
            n["indice"], cellule(n["lag_mois"], 0, " mois"), cellule(n["pearson_r"], 2),
            "[%s ; %s]" % (cellule(bas, 2), cellule(haut, 2)), cellule(n["p_neff"], 3),
            cellule(ligne["spearman_r"] if ligne is not None else None, 2),
            VERDICTS.get(n["verdict"], n["verdict"])])
    if notes:
        tete = notes[0]
        ligne = _ligne(dfm, tete["indice"], tete["lag_mois"])
        bas, haut = ic_fisher(ligne["pearson_r"], ligne["n_eff"])
        reg.ajouter(k + "_top_indice", tete["indice"], "indice du lien le plus solide (%s)"
                    % LIBELLES[phase], "correle", SRC, PERIODE, format="texte")
        reg.ajouter(k + "_top_indice_nom", NOMS_INDICES.get(tete["indice"], tete["indice"]),
                    "nom de l'indice (%s)" % LIBELLES[phase], "correle", SRC, PERIODE,
                    format="texte")
        reg.ajouter(k + "_top_lag", tete["lag_mois"], "décalage du lien le plus solide (mois)",
                    "correle", SRC, PERIODE, format="entier", suffixe=" mois")
        reg.ajouter(k + "_top_r", tete["pearson_r"], "r de Pearson du lien le plus solide",
                    "correle", SRC, PERIODE, format="signe", decimales=2)
        reg.ajouter_si(k + "_top_ic_bas", bas, "borne basse de l'IC 95 %", "correle", SRC,
                       PERIODE, format="signe", decimales=2)
        reg.ajouter_si(k + "_top_ic_haut", haut, "borne haute de l'IC 95 %", "correle", SRC,
                       PERIODE, format="signe", decimales=2)
        p_top = tete["p_neff"]
        reg.ajouter(k + "_top_p", "< 0,001" if p_top < 0.001 else nombre_fr(p_top, 3),
                    "p-value corrigée (n_eff)", "correle", SRC, PERIODE, format="texte")
        reg.ajouter(k + "_top_verdict", VERDICTS.get(tete["verdict"], tete["verdict"]),
                    "verdict de robustesse", "correle", SRC,
                    PERIODE, format="texte")
        plus, moins = SENS.get(metrique, ("plus marquées", "moins marquées"))
        sens = plus if tete["pearson_r"] < 0 else moins
        reg.ajouter(k + "_top_sens", sens, "sens du lien (si l'indice est plus froid)",
                    "correle", SRC, PERIODE, format="texte")
        c.paragraphe("analyse",
                     _p(phase, "PHASE. Sur {{fait:P_n_tests}} corrélations testées, "
                        "{{fait:P_n_sig}} restent significatives après correction de "
                        "l'autocorrélation (le seul hasard en produirait "
                        "{{fait:P_attendues}}) : {{fait:P_verdict}}. Le lien le plus solide associe "
                        "{{fait:P_top_indice}} ({{fait:P_top_indice_nom}}), {{fait:P_top_lag}} "
                        "avant la phase, à {{fait:metrique_libelle}} : r = {{fait:P_top_r}}, "
                        "intervalle de confiance à 95 % [{{fait:P_top_ic_bas}} ; "
                        "{{fait:P_top_ic_haut}}], p = {{fait:P_top_p}} "
                        "({{fait:P_top_verdict}})."),
                     "correle")
    else:
        c.paragraphe("analyse",
                     _p(phase, "PHASE. Sur {{fait:P_n_tests}} corrélations testées, "
                        "{{fait:P_n_sig}} restent significatives après correction (le seul "
                        "hasard en produirait {{fait:P_attendues}}) : {{fait:P_verdict}}. "
                        "Aucun lien n'est retenu pour cette phase."),
                     "correle")
    if lignes_tab:
        c.visuels.append(("analyse", tableau(
            ["Indice", "Décalage", "r", "IC 95 %", "p (n_eff)", "Spearman", "Robustesse"],
            lignes_tab, "Corrélations significatives : %s" % LIBELLES[phase],
            "Corrélations significatives après correction AR1, classées par robustesse "
            "(robuste = AR1 + Spearman + décalage voisin cohérent). r < 0 : pluies extrêmes plus "
            "intenses quand l'indice est plus froid.",
            "r de Pearson (sans unité)", PERIODE, "%s ; %s" % (tf.SOURCE_CHIRPS, tf.SOURCE_OISST),
            statut="correle")))
    spec, _ = outil_graph.construire({"type": "correlation_heatmap", "phase": phase,
                                      "metric": metrique}, data)
    c.visuels.append(("analyse", figure(
        spec, "Corrélations indices SST / pluies extrêmes : %s" % LIBELLES[phase],
        "r de Pearson entre chaque indice (lignes) moyenné sur les mois précédant la phase et "
        "%s, selon le décalage (colonnes). Étoiles : significatif après correction AR1 "
        "(* < 0,05 ; ** < 0,01 ; *** < 0,001)." % METRIQUES[metrique],
        "r de Pearson (sans unité)", PERIODE, "%s ; %s" % (tf.SOURCE_CHIRPS, tf.SOURCE_OISST),
        statut="correle")))
    return {"notes": notes, "bilan": bilan}


def _configurations(c, data):
    reg = c.registre
    try:
        res = outil_clusters.run({"phase": "Toutes phases"}, data)
    except Exception:
        c.limites_specifiques.append("La typologie des configurations océaniques n'est pas "
                                     "disponible sur ce serveur.")
        return
    m = res.get("methode", {})
    reg.ajouter_si("k_clusters", m.get("k_retenu"), "configurations océaniques (K-Means)",
                   "methode", "NOAA OISST v2 (K-Means)", PERIODE, format="entier")
    reg.ajouter_si("silhouette", m.get("silhouette"), "silhouette du K-Means (0 = aucune "
                   "séparation, 1 = parfaite)", "methode", "NOAA OISST v2 (K-Means)", PERIODE,
                   decimales=2)
    clusters = res.get("clusters", [])
    if clusters:
        c.visuels.append(("analyse", tableau(
            ["Configuration", "Événements", "Part", "Intensité max. moyenne", "État océanique"],
            [["C%d" % x["cluster"], cellule(x["n_evenements"], 0), cellule(x["part_pct"], 1, " %"),
              cellule(x["max_precip_moyen_mm"], 1, " mm"), x.get("etat_oceanique") or "mixte"]
             for x in sorted(clusters, key=lambda x: -x["n_evenements"])],
            "Configurations océaniques types (toutes phases)",
            "Typologie K-Means des champs de SST globaux du jour de chaque événement extrême ; "
            "chaque configuration est rattachée à l'un des 4 états saisonniers robustes.",
            "nombre d'événements ; % ; mm/jour", PERIODE, tf.SOURCE_OISST, statut="observe")))
        grand = max(clusters, key=lambda x: x["n_evenements"])
        reg.ajouter("cluster_principal", "C%d" % grand["cluster"], "configuration la plus "
                    "fréquente", "observe", "NOAA OISST v2 (K-Means)", PERIODE, format="texte")
        reg.ajouter("cluster_principal_part", grand["part_pct"], "part des événements de la "
                    "configuration la plus fréquente", "observe", "NOAA OISST v2 (K-Means)",
                    PERIODE, format="pct", decimales=0)
        reg.ajouter("cluster_principal_etat", grand.get("etat_oceanique") or "mixte",
                    "état océanique de la configuration la plus fréquente", "observe",
                    "NOAA OISST v2 (K-Means)", PERIODE, format="texte")
        try:
            spec, _ = outil_cartes.construire({"type": "sst_cluster", "phase": "Toutes phases",
                                               "cluster": int(grand["cluster"])}, {})
            c.visuels.append(("analyse", figure(
                spec, "Anomalies de SST de la configuration %s" % ("C%d" % grand["cluster"]),
                "Champ moyen d'anomalie de température de surface de la mer (60°S-60°N) des "
                "événements de la configuration la plus fréquente ; cadres : zones des indices.",
                "°C (anomalie)", PERIODE, tf.SOURCE_OISST, statut="observe")))
        except Exception:
            pass
    if ETATS.is_file():
        try:
            etats = json.loads(ETATS.read_text(encoding="utf-8")).get("etats", [])
        except (OSError, ValueError):
            etats = []
        if etats:
            c.visuels.append(("analyse", tableau(
                ["État", "Description", "Saisons", "Exemples d'années"],
                [[e["nom"], e.get("description", ""), cellule(e.get("n_saisons"), 0),
                  ", ".join(str(a) for a in (e.get("annees") or [])[:6])] for e in etats],
                "Les quatre états océaniques saisonniers",
                "États obtenus par classification des champs de SST saisonniers et nommés par "
                "une règle fixe sur les indices (Niño 3.4, océan Indien).",
                "nombre de saisons", PERIODE, tf.SOURCE_OISST, statut="observe")))


def collecter(spec, data, gazetteer=None):
    metrique = spec.metrique
    reg = RegistreFaits()
    phases = PHASES if spec.phase in ("Toutes phases", "All_phases") else [spec.phase]
    c = Collecte(registre=reg, titre="Téléconnexions océan / pluies extrêmes",
                 sous_titre="Indices de température de surface de la mer et %s, %s"
                 % (METRIQUES[metrique], PERIODE), zone="Sénégal", periode=PERIODE)
    c.sources = ["CHIRPS", "OISST"]
    c.limite("couverture_oisst", "multiplicite_tests", "metrique_intensite", "resolution",
             "clusters_descriptifs", "couverture_chirps")
    c.mentions.append(Encadre(tf.AVERTISSEMENT_CORRELATION, "avertissement",
                              "Corrélation n'est pas prévision"))
    reg.ajouter("metrique_libelle", METRIQUES[metrique], "métrique étudiée", "methode", SRC,
                PERIODE, format="texte")
    reg.ajouter("n_indices", 11, "indices océaniques testés", "methode", tf.SOURCE_OISST, PERIODE,
                format="entier")
    reg.ajouter("n_saisons", 41, "saisons analysées", "methode", SRC, PERIODE, format="entier")
    public = tf.PUBLICS[spec.public]
    c.paragraphe("contexte",
                 "Ce rapport examine les liens statistiques entre la température de surface des "
                 "océans (Pacifique, Atlantique, océan Indien) et {{fait:metrique_libelle}} au "
                 "Sénégal, sur {{fait:n_saisons}} saisons, à l'intention des %s. Il décrit des "
                 "associations observées dans le passé : il ne fournit pas de prévision." % public)
    resultats = {}
    for phase in phases:
        r = _phase(c, data, phase, metrique)
        if r is not None:
            resultats[phase] = r
    if not resultats:
        raise CollecteImpossible("Aucune corrélation disponible pour cette métrique.")
    robustes = [(p, n) for p, r in resultats.items() for n in r["notes"]
                if n["verdict"] == "robuste"]
    reg.ajouter("n_robustes_total", len(robustes), "corrélations robustes, toutes phases "
                "étudiées", "correle", SRC, PERIODE, format="entier")
    bassins = sorted({outil_ana._bassin(n["indice"]) for _, n in robustes})
    if bassins:
        reg.ajouter("bassins_robustes", enumerer([BASSINS.get(b, b) for b in bassins]), "bassins océaniques des liens "
                    "robustes", "correle", SRC, PERIODE, format="texte")
    c.paragraphe("resume", "Sur {{fait:n_indices}} indices océaniques testés à des décalages "
                 "de 0 à 5 mois, {{fait:n_robustes_total}} corrélations résistent aux trois "
                 "critères de robustesse.%s" % (
                     " Elles concernent : {{fait:bassins_robustes}}." if bassins else ""),
                 "correle")
    for phase in resultats:
        k = COURTS[phase]
        if k + "_top_indice" in reg:
            c.paragraphe("resume", _p(phase, "PHASE : lien le plus solide avec "
                                      "{{fait:P_top_indice}} (r = {{fait:P_top_r}}, "
                                      "{{fait:P_top_verdict}}) ; les pluies extrêmes tendent à "
                                      "être {{fait:P_top_sens}} quand cet indice est plus froid "
                                      "que la normale."), "correle")
        else:
            c.paragraphe("resume", "%s : aucun lien solide." % (
                LIBELLES[phase][0].upper() + LIBELLES[phase][1:]), "correle")
    c.paragraphe("resume", "Ces liens sont des corrélations : ils ne permettent pas, seuls, "
                 "d'annoncer l'intensité d'une saison.", None)
    if "Phase_2_pleine" in resultats and "p2_top_indice" in reg:
        spec_l, _ = outil_graph.construire({
            "type": "correlation_lags", "phase": "Phase_2_pleine", "metric": metrique,
            "indices": list(dict.fromkeys(n["indice"] for n in
                                          resultats["Phase_2_pleine"]["notes"]))[:3]}, data)
        c.visuels.append(("analyse", figure(
            spec_l, "Corrélation selon le décalage : cœur de saison",
            "r de Pearson en fonction du décalage (mois entre l'indice et la phase) pour les "
            "indices les plus liés ; point plein = significatif après correction AR1.",
            "r de Pearson (sans unité)", PERIODE, "%s ; %s" % (tf.SOURCE_CHIRPS, tf.SOURCE_OISST),
            statut="correle")))
    _configurations(c, data)
    if "k_clusters" in reg:
        c.paragraphe("analyse", "Configurations océaniques types. Les champs de SST des jours "
                     "d'événement se répartissent en {{fait:k_clusters}} configurations "
                     "(K-Means, silhouette {{fait:silhouette}} : séparation faible). La plus "
                     "fréquente, {{fait:cluster_principal}}, regroupe "
                     "{{fait:cluster_principal_part}} des événements et relève de l'état "
                     "{{fait:cluster_principal_etat}}.", "observe")
    c.paragraphe("conclusions", "Les liens les plus solides relèvent de {{fait:bassins_robustes}}"
                 " ; ils décrivent un contexte océanique favorable ou défavorable, pas une "
                 "échéance." if bassins else "Aucun lien ne résiste à l'ensemble des critères "
                 "de robustesse : les températures océaniques n'apportent pas ici d'indication "
                 "fiable sur l'intensité des pluies extrêmes.", "correle")
    c.recommandations = [
        "Ne pas utiliser ces corrélations comme une prévision : pour la saison à venir, se "
        "référer au bulletin de veille pré-saison et aux prévisions officielles de l'ANACIM.",
        "Suivre les indices océaniques aux liens robustes comme indicateurs de contexte, "
        "quelques mois avant la phase concernée, sans en tirer de décision automatique.",
        "Pour la recherche : confirmer ces liens sur des données indépendantes (autres "
        "produits de pluie, stations) et sur la pluie totale de la saison."]
    if spec.public == "technique":
        c.consignes.append("Public technique: garder r, IC, p_neff et le bilan face au hasard "
                           "dans le resume.")
    return c
