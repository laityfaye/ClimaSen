"""Rapport historique: les evenements de pluie extreme 1981-2023.

Catalogue lu par le chargeur du dashboard (1317 evenements). Un evenement est
une JOURNEE ou une partie du territoire depasse 2 sigma: il est rattache a
une zone par l'endroit ou son intensite a ete maximale (max_intensity_region,
max_intensity_department). Le catalogue ne descend pas sous le departement:
pour un arrondissement ou une commune, on decrit son departement, et la
frequence locale vient de la grille CHIRPS (indice de risque, alea).

Tendance: pente de Sen et test de Mann-Kendall, comme analyze_extreme_events.
"""
import numpy as np
import pandas as pd
from scipy import stats

from ...tools import cartes as outil_cartes
from ...tools.common import normalise
from .. import textes_fixes as tf
from ..faits import RegistreFaits, date_fr, nombre_fr
from . import Collecte, CollecteImpossible, cellule, figure, fini, tableau

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
PHASES = {"Phase_1_debut": "début de saison (mai-juin)",
          "Phase_2_pleine": "cœur de saison (juillet-août)",
          "Phase_3_fin": "fin de saison (septembre-octobre)"}
SRC = "CHIRPS v2 (catalogue CLIMAT-SEN)"


def _filtre_zone(df, lieu, data):
    """(sous-ensemble, libelle de rattachement, niveau effectif)."""
    if lieu.niveau == "pays":
        return df, "le Sénégal", "pays"
    if lieu.niveau == "region":
        masque = df["max_intensity_region"].fillna("").map(normalise) == normalise(lieu.nom)
        return df[masque], "la région de %s" % lieu.nom, "region"
    dep = lieu.departement or lieu.nom
    masque = df["max_intensity_department"].fillna("").map(normalise) == normalise(dep)
    return df[masque], "le département de %s" % dep, "departement"


def _serie(df, debut, fin):
    annees = pd.Index(range(debut, fin + 1), name="year")
    return df.groupby("year").size().reindex(annees, fill_value=0)


def collecter(spec, data, gazetteer=None):
    tout = data["events"]
    debut, fin = spec.annee_debut, spec.annee_fin
    periode = "%d-%d" % (debut, fin)
    base = tout[tout["year"].between(debut, fin)]
    if spec.phase != "Toutes phases":
        base = base[base["phase"] == spec.phase]
    sel, rattachement, niveau = _filtre_zone(base, spec.lieu, data)
    reg = RegistreFaits()
    c = Collecte(registre=reg, titre="Historique des pluies extrêmes",
                 sous_titre="%s, %s%s" % (spec.lieu.libelle()[0].upper() + spec.lieu.libelle()[1:], periode,
                                          "" if spec.phase == "Toutes phases"
                                          else ", " + PHASES[spec.phase]),
                 zone=spec.lieu.libelle(), periode=periode)
    c.sources = ["CHIRPS", "OCHA"]
    c.limite("couverture_chirps", "resolution", "evenements_nationaux", "tendance")
    if (debut, fin) != (1981, 2023):
        c.limite("periode_reduite")
    if spec.lieu.niveau in ("arrondissement", "commune"):
        c.limites_specifiques.append(
            "Le catalogue d'événements ne descend pas sous le département : les événements "
            "décrits sont ceux dont l'intensité maximale est tombée dans le département de %s."
            % (spec.lieu.departement or spec.lieu.nom))

    reg.ajouter("periode_debut", debut, "première année", "methode", SRC, periode, format="annee")
    reg.ajouter("periode_fin", fin, "dernière année", "methode", SRC, periode, format="annee")
    reg.ajouter("rattachement", rattachement, "zone de rattachement des événements", "methode",
                SRC, periode, format="texte")
    reg.ajouter("n_national", len(base), "événements extrêmes au Sénégal sur la période",
                "observe", SRC, periode, format="entier")
    reg.ajouter("n_zone", len(sel), "événements dont l'intensité maximale est dans la zone",
                "observe", SRC, periode, format="entier")
    if len(base):
        reg.ajouter("part_zone", len(sel) / float(len(base)),
                    "part des événements nationaux rattachés à la zone", "observe", SRC, periode,
                    format="fraction_pct", decimales=0)
    n_ans = fin - debut + 1
    reg.ajouter("n_annees", n_ans, "nombre d'années", "methode", SRC, periode, format="entier")
    reg.ajouter("par_an_zone", len(sel) / float(n_ans), "événements par an en moyenne (zone)",
                "observe", SRC, periode, decimales=1)

    # Frequence locale de la grille (meme valeur que l'alea de l'indice).
    if spec.lieu.niveau in ("departement", "arrondissement", "commune"):
        v = data.get("vulnerabilite")
        if v is not None:
            if spec.lieu.niveau == "departement":
                t, code = v["departements"], spec.lieu.code
            else:
                t = v.get("arrondissements")
                code = spec.lieu.pcode_arrondissement or spec.lieu.code
            if t is not None:
                ligne = t[t["pcode"] == code]
                if len(ligne):
                    reg.ajouter_si("local_jours_2sigma", fini(ligne.iloc[0]["jours_anomalie_2sigma_an"]),
                                   "jours par an d'anomalie > 2 écarts-types sur la zone (grille)",
                                   "observe", tf.SOURCE_CHIRPS, "1981-2023", decimales=1,
                                   suffixe=" jours/an")
                    reg.ajouter_si("local_jours_50mm", fini(ligne.iloc[0]["jours_50mm_an"]),
                                   "jours par an de pluie > 50 mm sur la zone (grille)",
                                   "observe", tf.SOURCE_CHIRPS, "1981-2023", decimales=1,
                                   suffixe=" jours/an")

    public = tf.PUBLICS[spec.public]
    c.paragraphe("contexte",
                 "Ce rapport retrace les événements de pluie extrême observés de "
                 "{{fait:periode_debut}} à {{fait:periode_fin}} pour %s, à l'intention des %s. "
                 "Il s'appuie sur le catalogue d'événements de la plateforme CLIMAT-SEN, établi "
                 "à partir des pluies journalières CHIRPS." % (spec.lieu.avec_article(), public))

    if len(sel) == 0:
        c.paragraphe("resume", "Aucun des {{fait:n_national}} événements extrêmes recensés au "
                     "Sénégal sur {{fait:periode_debut}}-{{fait:periode_fin}} n'a eu son "
                     "intensité maximale dans {{fait:rattachement}}.", "observe")
        if "local_jours_2sigma" in reg:
            c.paragraphe("resume", "La grille de pluie y enregistre néanmoins en moyenne "
                         "{{fait:local_jours_2sigma}} d'anomalie supérieure à 2 écarts-types et "
                         "{{fait:local_jours_50mm}} de pluie supérieure à 50 mm : des pluies "
                         "intenses locales surviennent, sans être le cœur d'un événement "
                         "régional.", "observe")
        c.paragraphe("analyse", "Les événements extrêmes de la période touchent surtout le "
                     "sud et l'est du pays ; la carte et le classement ci-dessous situent la "
                     "zone dans ce contexte national.", "observe")
        _contexte_national(c, base, periode)
        c.paragraphe("conclusions", "La zone n'a pas été le centre d'un événement extrême "
                     "recensé sur la période ; cela n'exclut pas des pluies intenses locales.",
                     "observe")
        c.recommandations = [
            "Ne pas conclure à une absence de risque : les épisodes intenses très localisés, "
            "notamment urbains, peuvent échapper à une détection à l'échelle de 0,25°.",
            "Compléter ce bilan par les relevés pluviométriques locaux et l'historique des "
            "inondations tenu par les services techniques et l'ANACIM."]
        return c

    # --- comptes et records ---------------------------------------------------
    for ph, lib in PHASES.items():
        reg.ajouter("n_" + ph, int((sel["phase"] == ph).sum()), "événements en " + lib,
                    "observe", SRC, periode, format="entier")
    rec = sel.loc[sel["max_precip"].idxmax()]
    reg.ajouter("record_mm", rec["max_precip"], "intensité maximale observée", "observe", SRC,
                periode, decimales=1, suffixe=" mm/jour")
    reg.ajouter("record_date", str(rec["date"])[:10], "date de l'intensité maximale", "observe",
                SRC, periode, format="date")
    reg.ajouter("moy_max_mm", sel["max_precip"].mean(), "intensité maximale moyenne des événements",
                "observe", SRC, periode, decimales=1, suffixe=" mm/jour")
    reg.ajouter("moy_couverture", sel["coverage_percent"].mean(),
                "couverture spatiale moyenne des événements", "observe", SRC, periode,
                format="pct", decimales=0)
    mois = sel.groupby("month").size()
    m_top = int(mois.idxmax())
    reg.ajouter("mois_top", MOIS[m_top - 1], "mois le plus touché", "observe", SRC, periode,
                format="texte")
    reg.ajouter("n_mois_top", int(mois.max()), "événements du mois le plus touché", "observe",
                SRC, periode, format="entier")
    serie = _serie(sel, debut, fin)
    a_top = int(serie.idxmax())
    reg.ajouter("annee_top", a_top, "année la plus touchée", "observe", SRC, periode,
                format="annee")
    reg.ajouter("n_annee_top", int(serie.max()), "événements de l'année la plus touchée",
                "observe", SRC, periode, format="entier")
    reg.ajouter("annees_sans", int((serie == 0).sum()), "années sans événement", "observe", SRC,
                periode, format="entier")

    # --- tendance --------------------------------------------------------------
    tendance = None
    x = serie.index.to_numpy(dtype=float)
    y = serie.to_numpy(dtype=float)
    if len(serie) >= 8 and not np.allclose(y, y[0]):
        pente, ordonnee = stats.theilslopes(y, x)[:2]
        tau, p = stats.kendalltau(x, y)
        reg.ajouter("sen_decennie", pente * 10, "pente de Sen (événements par décennie)",
                    "observe", SRC, periode, format="signe", decimales=2,
                    suffixe=" événement(s) par décennie")
        reg.ajouter("p_mk", "< 0,001" if p < 0.001 else nombre_fr(p, 3),
                    "p-value du test de Mann-Kendall", "observe", SRC, periode, format="texte")
        sig = p < 0.05
        sens = "hausse" if pente > 0 else ("baisse" if pente < 0 else "stabilité")
        reg.ajouter("tendance_verdict",
                    ("%s significative" % sens) if sig else "pas de tendance significative",
                    "verdict de tendance (seuil 5 %)", "observe", SRC, periode, format="texte")
        tendance = {"nom": "tendance (pente de Sen)",
                    "y": [round(ordonnee + pente * a, 3) for a in serie.index]}
        moitie = (debut + fin) // 2
        p1 = serie[serie.index <= moitie].mean()
        p2 = serie[serie.index > moitie].mean()
        reg.ajouter("moitie1", "%d-%d" % (debut, moitie), "première moitié", "methode", SRC,
                    periode, format="texte")
        reg.ajouter("moitie2", "%d-%d" % (moitie + 1, fin), "seconde moitié", "methode", SRC,
                    periode, format="texte")
        reg.ajouter("par_an_moitie1", p1, "événements par an, première moitié", "observe", SRC,
                    periode, decimales=1)
        reg.ajouter("par_an_moitie2", p2, "événements par an, seconde moitié", "observe", SRC,
                    periode, decimales=1)

    # --- texte gabarit ----------------------------------------------------------
    c.paragraphe("resume", "De {{fait:periode_debut}} à {{fait:periode_fin}}, "
                 "{{fait:n_zone}} événements de pluie extrême ont eu leur intensité maximale "
                 "dans {{fait:rattachement}}, sur {{fait:n_national}} recensés au Sénégal, "
                 "soit {{fait:par_an_zone}} par an en moyenne.", "observe")
    c.paragraphe("resume", "Le maximum observé atteint {{fait:record_mm}} le "
                 "{{fait:record_date}}. Le mois le plus touché est {{fait:mois_top}}, et "
                 "l'année la plus touchée {{fait:annee_top}} ({{fait:n_annee_top}} événements).",
                 "observe")
    if "tendance_verdict" in reg:
        c.paragraphe("resume", "Sur la période, le nombre annuel d'événements montre : "
                     "{{fait:tendance_verdict}} (pente de Sen {{fait:sen_decennie}}, p = "
                     "{{fait:p_mk}}).", "observe")
    c.paragraphe("analyse", "Répartition saisonnière. On compte {{fait:n_Phase_1_debut}} "
                 "événements en début de saison (mai-juin), {{fait:n_Phase_2_pleine}} au cœur "
                 "de la saison (juillet-août) et {{fait:n_Phase_3_fin}} en fin de saison "
                 "(septembre-octobre).", "observe")
    c.paragraphe("analyse", "Intensité et étendue. L'intensité maximale moyenne des événements "
                 "est de {{fait:moy_max_mm}} ; chacun couvre en moyenne {{fait:moy_couverture}} "
                 "du territoire national.", "observe")
    if "par_an_moitie1" in reg:
        c.paragraphe("analyse", "Évolution. La zone a connu {{fait:par_an_moitie1}} événement(s) "
                     "par an en {{fait:moitie1}} contre {{fait:par_an_moitie2}} en "
                     "{{fait:moitie2}}." + (" {{fait:annees_sans}} années n'en ont connu aucun."
                                        if reg["annees_sans"].valeur > 1 else
                                        " Une seule année n'en a connu aucun."
                                        if reg["annees_sans"].valeur == 1 else
                                        " Chaque année de la période en a connu au moins un."),
                     "observe")
    if "local_jours_2sigma" in reg:
        c.paragraphe("analyse", "Fréquence locale. Sur la grille de pluie, la zone compte en "
                     "moyenne {{fait:local_jours_2sigma}} d'anomalie supérieure à 2 écarts-types "
                     "et {{fait:local_jours_50mm}} de pluie supérieure à 50 mm (mai-octobre).",
                     "observe")

    # --- visuels ----------------------------------------------------------------
    c.visuels.append(("analyse", figure(
        {"genre": "barres", "hauteur_pouces": 2.4,
         "donnees": {"categories": [int(a) for a in serie.index],
                     "valeurs": [int(v) for v in serie.values], "x_label": "année",
                     "y_label": "nombre d'événements", "tendance": tendance}},
        "Événements extrêmes par an",
        "Nombre annuel d'événements dont l'intensité maximale est dans %s%s."
        % (rattachement, " ; en pointillé, la tendance (pente de Sen)" if tendance else ""),
        "nombre d'événements", periode, tf.SOURCE_CHIRPS, statut="observe")))
    mois_presents = [m for m in range(1, 13) if mois.get(m, 0) > 0]
    c.visuels.append(("analyse", figure(
        {"genre": "barres", "hauteur_pouces": 2.0,
         "donnees": {"categories": [MOIS[m - 1] for m in mois_presents],
                     "valeurs": [int(mois.get(m, 0)) for m in mois_presents],
                     "x_label": "mois", "y_label": "nombre d'événements"}},
        "Saisonnalité des événements extrêmes",
        "Nombre d'événements par mois sur la période, %s." % rattachement,
        "nombre d'événements", periode, tf.SOURCE_CHIRPS, statut="observe")))
    top = sel.sort_values("max_precip", ascending=False).head(10)
    c.visuels.append(("analyse", tableau(
        ["Date", "Phase", "Intensité max.", "Anomalie max.", "Couverture", "Zone du maximum"],
        [[date_fr(str(r["date"])[:10]), PHASES.get(r["phase"], r["phase"]).split(" (")[0],
          cellule(r["max_precip"], 1, " mm"), cellule(r["max_anomaly"], 1, " σ"),
          cellule(r["coverage_percent"], 0, " %"),
          "%s (%s)" % (r["max_intensity_department"], r["max_intensity_region"])]
         for _, r in top.iterrows()],
        "Les dix événements les plus intenses",
        "Événements classés par intensité maximale journalière ; la couverture est la part du "
        "territoire en anomalie supérieure à 2 écarts-types.",
        "mm/jour ; σ (écarts-types) ; % du territoire", periode, tf.SOURCE_CHIRPS,
        statut="observe")))
    _contexte_national(c, base, periode)

    # --- conclusions --------------------------------------------------------------
    c.paragraphe("conclusions", "Les pluies extrêmes de la zone se concentrent en "
                 "{{fait:mois_top}} ; l'intensité maximale observée est de {{fait:record_mm}}.",
                 "observe")
    recos = ["Concentrer la vigilance opérationnelle (veille, curage préalable, disponibilité "
             "des équipes) sur le mois de {{fait:mois_top}} et les semaines qui l'encadrent."]
    if reg.faits.get("n_Phase_1_debut") and reg["n_Phase_1_debut"].valeur > 0:
        recos.append("Être prêt dès le début de saison : {{fait:n_Phase_1_debut}} événements "
                     "extrêmes sont survenus en mai-juin, avant le cœur de l'hivernage.")
    if "tendance_verdict" in reg and "significative" in reg["tendance_verdict"].valeur \
            and "pas de" not in reg["tendance_verdict"].valeur:
        recos.append("Intégrer la tendance observée ({{fait:tendance_verdict}}) dans le "
                     "dimensionnement des ouvrages et des plans de contingence.")
    recos.append("Compléter ce bilan par les relevés pluviométriques locaux et l'historique des "
                 "inondations tenu par les services techniques et l'ANACIM.")
    c.recommandations = recos
    return c


def _contexte_national(c, base, periode):
    """Carte de frequence et classement des regions: la zone dans le pays."""
    if base.empty:
        raise CollecteImpossible("Aucun événement extrême sur la période demandée.")
    comptes = base.groupby("max_intensity_region").size().sort_values(ascending=False)
    c.visuels.append(("analyse", figure(
        {"genre": "barres", "hauteur_pouces": max(1.8, 0.22 * len(comptes) + 0.6),
         "donnees": {"categories": list(comptes.index), "valeurs": [int(v) for v in comptes],
                     "x_label": "région", "y_label": "nombre d'événements",
                     "horizontal": True}},
        "Régions où l'intensité des événements a été maximale",
        "Nombre d'événements extrêmes selon la région où l'intensité journalière a été la plus "
        "forte (ensemble du Sénégal).", "nombre d'événements", periode, tf.SOURCE_CHIRPS,
        statut="observe")))
    try:
        phase = None
        phases = base["phase"].unique()
        if len(phases) == 1:
            phase = phases[0]
        params = {"type": "frequence_extremes"}
        if phase:
            params["phase"] = phase
        spec, _ = outil_cartes.construire(params, {"events": base})
        c.visuels.append(("analyse", figure(
            spec, "Fréquence des extrêmes par pixel",
            "Part des journées d'événement où chaque pixel dépasse 2 écarts-types de sa "
            "climatologie (ensemble des événements de la période).",
            "% des journées d'événement", periode, tf.SOURCE_CHIRPS, statut="observe")))
    except Exception:  # la grille CHIRPS peut manquer sur un serveur allege
        c.limites_specifiques.append("La carte de fréquence par pixel n'a pas pu être produite "
                                     "(grille CHIRPS indisponible sur ce serveur).")
