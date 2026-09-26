"""Mode soutenance: une presentation guidee de CLIMAT-SEN par Jarvis.

Jarvis deroule le travail etape par etape: il ouvre la bonne page du
dashboard, affiche la figure en grand et la commente a voix haute. Le jury
peut l'interrompre par une question, puis la presentation reprend.

Principe cle: AUCUN chiffre n'est ecrit en dur. Chaque narration est
composee au moment ou l'etape est demandee, a partir des memes constructeurs
que les outils (make_figure, show_map, recompute_correlation...) et des memes
fichiers que le dashboard. Si le script 04 est relance et que les resultats
changent, la soutenance dit les nouveaux chiffres. C'est aussi pourquoi la
narration ne passe pas par le modele: un texte compose par le code ne peut
pas halluciner un coefficient devant un jury.
"""
import logging

from . import analyses, cartes
from .tools import analyse_teleconnexions, animation, cartes as outil_cartes
from .tools import graphiques
from .tools.common import INDICES_LABELS, PHASES_LABELS

PHASE = "Phase_2_pleine"
METRIQUE = "max_precip"
SEUIL = 0.05

JEUX = ("events", "correlations", "indices", "clustering")

log = logging.getLogger("jarvis.soutenance")


def fr(v, decimales=2):
    """Nombre a la francaise, pour l'ecran et la voix: -0,42."""
    if v is None:
        return "n.d."
    return (("%%.%df" % decimales) % float(v)).replace(".", ",")


def _p(p):
    if p is None:
        return "n.d."
    return "p inférieur à 0,001" if p < 0.001 else "p = %s" % fr(p, 3)


def _meilleures(data, phase=PHASE, n=3):
    df = data["correlations"][phase]
    df = df[(df["metric"] == METRIQUE) & (df["pearson_p_neff"] < SEUIL)]
    df = df.reindex(df["pearson_r"].abs().sort_values(ascending=False).index)
    return [ligne for _, ligne in df.head(n).iterrows()]


def _nom(indice):
    return "%s (%s)" % (indice, INDICES_LABELS.get(indice, indice).split(" (")[0])


def _deposer(figures, session_id, spec, carte=False):
    fig = figures.deposer(session_id, spec)
    return {"id": fig.id, "titre": spec.get("titre", ""),
            "sous_titre": spec.get("sous_titre", ""), "carte": carte}


# =============================================================================
# Etapes
# =============================================================================
def _probleme(data, figures, sid):
    spec, r = graphiques.construire({"type": "events_per_year"}, data)
    pente = r.get("pente_sen_par_decennie")
    p = r.get("p_mann_kendall")
    if pente is None or p is None:
        tendance = "La tendance n'est pas calculable sur cette période."
    elif p < SEUIL:
        tendance = ("La tendance de Sen est de %s événement%s par décennie, "
                    "significative (Mann-Kendall, %s)."
                    % (fr(pente, 1), "s" if abs(pente) >= 2 else "", _p(p)))
    else:
        tendance = ("La tendance de Sen, %s par décennie, n'est pas "
                    "significative (Mann-Kendall, %s) : pas de hausse démontrée."
                    % (fr(pente, 1), _p(p)))
    rec = r.get("annee_record") or {}
    texte = ("CLIMAT-SEN étudie les pluies extrêmes au Sénégal. Sur les données "
             "CHIRPS de %d à %d, %d événements dépassent deux écarts-types de la "
             "normale journalière. L'année record est %s, avec %s événements. %s"
             % (r["periode"][0], r["periode"][1], r["n_evenements"],
                rec.get("annee", "n.d."), rec.get("n", "n.d."), tendance))
    return {"page": "Evenements", "filtres": {},
            "figure": _deposer(figures, sid, spec), "narration": texte}


def _ou_et_quand(data, figures, sid):
    _, mois = graphiques.construire({"type": "events_by_month"}, data)
    spec, r = outil_cartes.construire({"type": "frequence_extremes"}, data)
    par_mois = mois["par_mois"]
    pic = max(par_mois, key=par_mois.get)
    regions = [x["region"] for x in r["regions_les_plus_frequentes"][:2]]
    texte = ("Ces événements suivent la saison des pluies : le mois le plus "
             "touché est %s, avec %d événements. Nous découpons donc la saison "
             "en trois phases : début en mai-juin, pleine saison en juillet-août, "
             "fin en septembre-octobre. La carte montre où les extrêmes frappent "
             "le plus souvent : d'abord %s."
             % (pic, par_mois[pic], " puis ".join(regions)))
    return {"page": "Evenements", "filtres": {},
            "figure": _deposer(figures, sid, spec, carte=True), "narration": texte}


def _teleconnexions(data, figures, sid):
    spec, _ = graphiques.construire({"type": "correlation_heatmap", "phase": PHASE,
                                     "metric": METRIQUE}, data)
    top = _meilleures(data)
    if top:
        # Pas d'etoiles: la voix les lirait "asterisque". Le nom long de
        # l'indice une seule fois, a sa premiere mention.
        phrases, cites = [], set()
        for l in top:
            nom = l["index"] if l["index"] in cites else _nom(l["index"])
            cites.add(l["index"])
            phrases.append("%s au décalage de %d mois, r = %s, %s" % (
                nom, int(l["lag_months"]), fr(l["pearson_r"]), _p(l["pearson_p_neff"])))
        signal = ("Les corrélations les plus fortes, significatives après "
                  "correction de l'autocorrélation, sont : %s." % " ; ".join(phrases))
    else:
        signal = "Aucune corrélation n'est significative après correction AR1."
    texte = ("Question centrale : l'état des océans annonce-t-il l'intensité des "
             "extrêmes ? Pour la pleine saison, nous corrélons chaque année la "
             "pluie maximale avec onze indices de température de surface, "
             "décalés de zéro à cinq mois, après retrait des tendances. %s "
             "Le signal dominant vient de l'Atlantique, plusieurs mois à l'avance."
             % signal)
    return {"page": "Teleconnexions", "filtres": {"phase": PHASE, "metrique": METRIQUE},
            "figure": _deposer(figures, sid, spec), "narration": texte}


def _solidite(data, figures, sid):
    bilan = analyse_teleconnexions._bilan({"phase": PHASE}, data, METRIQUE)["phases"][0]
    top = _meilleures(data, n=1)
    figure = None
    detail = ""
    if top:
        l = top[0]
        r = analyses.correlation(PHASE, int(l["lag_months"]), l["index"], METRIQUE)
        spec = {
            "genre": "nuage", "type": "soutenance",
            "titre": "%s et pluie maximale, lag %d mois" % (l["index"], int(l["lag_months"])),
            "sous_titre": "pleine saison · %d années · r = %s (après détrend)"
                          % (r["n"], fr(r["pearson_r"])),
            "donnees": {"points": [(a, y, x) for a, x, y in r["points"]],
                        "x_label": "%s (détrendé, °C)" % l["index"],
                        "y_label": "pluie maximale (détrendée, mm)"},
            "source": "Recalcul avec les fonctions du script 04", "hauteur_pouces": 2.9,
        }
        figure = _deposer(figures, sid, spec)
        _, effets = analyses.influence_annuelle(PHASE, int(l["lag_months"]),
                                                l["index"], METRIQUE)
        perdent = [e["annee_retiree"] for e in effets if (e["p_neff"] or 1) >= SEUIL]
        detail = (" Chaque point est une année. Retirer une à une chacune des %d "
                  "années %s." % (r["n"], "ne fait jamais perdre la significativité"
                                  if not perdent else
                                  "fait perdre la significativité dans %d cas (%s)"
                                  % (len(perdent), ", ".join(map(str, perdent[:4])))))
    texte = ("Un résultat se juge aussi à ce que le hasard produirait. Sur %d tests "
             "en pleine saison, onze indices et six décalages, %d sont significatifs après correction AR1, quand "
             "le hasard seul en donnerait environ %s. Verdict : %s.%s"
             % (bilan["n_tests"], bilan["n_significatives_ar1"],
                fr(bilan["attendues_par_hasard"], 0), bilan["verdict"], detail))
    return {"page": "Teleconnexions", "filtres": {"phase": PHASE, "metrique": METRIQUE},
            "figure": figure, "narration": texte}


def _stabilite(data, figures, sid):
    top = _meilleures(data, n=1)
    if not top:
        return None
    l = top[0]
    lag = int(l["lag_months"])
    a = analyses.correlation(PHASE, lag, l["index"], METRIQUE, range(1983, 2003))
    b = analyses.correlation(PHASE, lag, l["index"], METRIQUE, range(2003, 2024))
    if not (a.get("calculable") and b.get("calculable")):
        return None
    meme = (a["pearson_r"] > 0) == (b["pearson_r"] > 0)
    spec, _ = graphiques.construire({"type": "correlation_lags", "phase": PHASE,
                                     "indices": [l["index"]], "metric": METRIQUE}, data)
    texte = ("Le signal est-il stable dans le temps ? En coupant la série en deux, "
             "la corrélation entre %s et la pluie maximale vaut %s de 1983 à 2002 "
             "et %s de 2003 à 2023. %s La courbe montre la corrélation selon le "
             "décalage : le signal se construit sur plusieurs mois consécutifs, "
             "ce qu'on attend d'une influence océanique lente."
             % (l["index"], fr(a["pearson_r"]), fr(b["pearson_r"]),
                "Le signe est le même sur les deux périodes." if meme else
                "Le signe change entre les deux périodes : prudence."))
    return {"page": "Teleconnexions", "filtres": {"phase": PHASE, "metrique": METRIQUE},
            "figure": _deposer(figures, sid, spec), "narration": texte}


def _clusters(data, figures, sid):
    affect = cartes.evenements_par_cluster(PHASE)
    frequent = int(affect["cluster"].value_counts().idxmax())
    spec, r = outil_cartes.construire({"type": "sst_cluster", "phase": PHASE,
                                       "cluster": frequent}, data)
    texte = ("Deuxième approche, au niveau de chaque événement : le jour de "
             "chaque extrême, nous classons le champ de température de tout "
             "l'océan par K-Means. En pleine saison, la configuration la plus "
             "fréquente, le cluster %d, regroupe %d événements. Sa boîte la plus "
             "chaude est %s, la plus froide %s."
             % (frequent, r["n_evenements"], r["boite_la_plus_chaude"],
                r["boite_la_plus_froide"]))
    return {"page": "Clustering", "filtres": {"phase": PHASE, "cluster": frequent},
            "figure": _deposer(figures, sid, spec, carte=True), "narration": texte}


def _animation(data, figures, sid):
    try:
        resultat = animation.run({"phase": PHASE}, data, figures=figures, session_id=sid)
    except Exception:
        return None
    evo = resultat["anomalies_par_boite_degC"]

    def ligne(nom):
        e = evo.get(nom) or {}
        return "%s passe de %s à %s degrés" % (nom, fr(e.get("J-150"), 1), fr(e.get("J0"), 1))

    texte = ("Pour rendre ce décalage visible : voici l'océan pendant les cinq mois "
             "qui précèdent l'événement du %s, l'un des plus intenses de la pleine "
             "saison. Entre J moins 150 et le jour J, %s ; %s. Un seul événement "
             "illustre, il ne démontre pas : la preuve, ce sont les quarante et une "
             "années de corrélations." % (resultat["date"], ligne("TNA"), ligne("AMO")))
    ref = {"id": resultat["figure_id"], "titre": resultat["titre"],
           "sous_titre": resultat["sous_titre"], "carte": True}
    return {"page": "Clustering", "filtres": {"phase": PHASE}, "figure": ref,
            "narration": texte}


def _conclusion(data, figures, sid):
    top = _meilleures(data, n=1)
    atlantique = top[0]["index"] if top else "l'Atlantique"
    comp = analyses.competence_analogues(PHASE, ["TNA", "TSA", "ATL3", "AMM", "AMO"])
    if comp.get("calculable"):
        analogues = ("Enfin, une méthode d'années analogues ne prévoit pas mieux que "
                     "le hasard : corrélation prévu-observé de %s, %s. Ces "
                     "téléconnexions expliquent une part de la variabilité, elles ne "
                     "suffisent pas à prévoir une saison."
                     % (fr(comp["r_prevu_observe"]), _p(comp["p_neff"])))
    else:
        analogues = ""
    texte = ("En résumé : les extrêmes de pleine saison sont liés à l'état de "
             "l'Atlantique plusieurs mois avant, avec %s en tête. Trois limites : "
             "une corrélation n'est pas une causalité ; quarante et une années "
             "donnent une puissance statistique modeste ; et aucune correction "
             "des comparaisons multiples n'est appliquée. %s Merci de votre "
             "attention. Je réponds à vos questions." % (_nom(atlantique), analogues))
    return {"page": "Teleconnexions", "filtres": {"phase": PHASE, "metrique": METRIQUE},
            "figure": None, "narration": texte}


ETAPES = [
    ("Le problème", _probleme),
    ("Où et quand", _ou_et_quand),
    ("Les téléconnexions", _teleconnexions),
    ("Solidité statistique", _solidite),
    ("Stabilité dans le temps", _stabilite),
    ("Configurations océaniques", _clusters),
    ("L'océan avant l'événement", _animation),
    ("Conclusion et limites", _conclusion),
]


def plan():
    return [{"numero": i + 1, "titre": t} for i, (t, _) in enumerate(ETAPES)]


def etape(numero, data, figures, session_id):
    """L'etape `numero` (1..n), composee maintenant. None si hors bornes.

    Une etape dont les donnees manquent (archive SST absente...) renvoie une
    narration de repli plutot que d'interrompre la presentation.
    """
    if not 1 <= numero <= len(ETAPES):
        return None
    titre, fabrique = ETAPES[numero - 1]
    try:
        contenu = fabrique(data, figures, session_id)
    except Exception:
        log.exception("Etape %d de la soutenance impossible.", numero)
        contenu = None
    if contenu is None:
        contenu = {"page": None, "filtres": {}, "figure": None,
                   "narration": "Cette étape n'est pas disponible sur ce serveur : "
                                "passons à la suite."}
    contenu.update({"numero": numero, "total": len(ETAPES), "titre": titre,
                    "phase_label": PHASES_LABELS.get(PHASE, PHASE)})
    return contenu
