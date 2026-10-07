"""Rapport de vulnerabilite: indice de risque (alea x exposition x vulnerabilite).

Memes tables et memes fonctions que l'outil get_priority_zones et la page
Vulnerabilite: la fiche d'une zone est construite par vulnerabilite._fiche,
la fiabilite par vulnerabilite._fiabilite, la carte par show_map.

Cinq echelles de demande: pays, region, departement, arrondissement,
commune. L'indice n'existe pas a la commune: une commune est decrite par son
arrondissement (drapeau echelle_arrondissement), seule sa population vient
de la commune elle-meme (RGPH-5).
"""
from ...tools import cartes as outil_cartes
from ...tools import vulnerabilite as outil_vul
from ...tools.common import normalise
from .. import textes_fixes as tf
from ..document import Encadre
from . import Collecte, CollecteImpossible, cellule, figure, fini, tableau

PERIODE = "aléa 1981-2023 ; population 2023"
UNITE_RANG = "rang centile (0 = plus faible, 1 = plus fort)"
LIBELLES_COMPOSANTE = {"A_alea": "l'aléa", "E_exposition": "l'exposition",
                       "V_vulnerabilite": "la vulnérabilité"}
COURTS = {"A_alea": "Aléa", "E_exposition": "Exposition", "V_vulnerabilite": "Vulnérabilité"}

RECO_DOMINANTE = {
    "A_alea": "Les pluies extrêmes y sont plus fréquentes qu'ailleurs : prioriser le curage "
              "et l'entretien des ouvrages de drainage avant juillet, et suivre de près les "
              "bulletins de l'ANACIM pendant le cœur de saison (juillet-septembre).",
    "E_exposition": "La population exposée est élevée : mettre à jour les plans de contingence "
                    "des quartiers les plus denses, identifier les sites d'accueil temporaires et "
                    "organiser l'information des habitants avant la saison.",
    "V_vulnerabilite": "Les ménages y sont plus vulnérables : cibler l'appui (information, "
                       "prépositionnement de vivres et de kits, accès aux abris) vers les ménages "
                       "les plus pauvres.",
}
RECO_TOUJOURS = (
    "Croiser ce classement avec l'historique local des inondations et l'expertise des services "
    "techniques avant toute décision d'investissement : l'indice ne retrouve pas les "
    "inondations documentées."
)
RECO_DAKAR = (
    "Dans la région de Dakar, ne pas lire un rang bas comme une absence de risque : "
    "l'exposition y est la plus forte du pays et les inondations urbaines y sont récurrentes ; "
    "les plans d'assainissement et de gestion des eaux pluviales restent prioritaires."
)


def _palier(rang, sur):
    part = rang / float(sur)
    if part <= 0.1:
        return "parmi les zones les plus prioritaires du pays"
    if part <= 0.33:
        return "dans le tiers des zones les plus prioritaires"
    if part <= 0.66:
        return "dans la moyenne nationale"
    return "dans le tiers des zones les moins prioritaires selon l'indice"


def _table(v, niveau):
    t = v["departements"] if niveau == "departements" else v.get("arrondissements")
    if t is None:
        raise CollecteImpossible("L'indice par arrondissement n'a pas été calculé (script 27).")
    t = t.copy()
    t["nom"] = (t["departement"] if niveau == "departements" else t["arrondissement"]).fillna(
        "Sans nom")
    return t


def _fiche_faits(c, r, niveau, n, prefixe="zone"):
    """Faits de la fiche d'une zone (memes valeurs que get_priority_zones)."""
    reg = c.registre
    f = outil_vul._fiche(r, niveau, n)
    b = f["chiffres_bruts"]
    s_i, s_p = tf.SOURCE_INDICE, tf.SOURCE_RGPH5
    reg.ajouter(prefixe + "_nom", f["nom"], "nom de la zone", "observe", s_p, "2023",
                format="texte")
    reg.ajouter_si(prefixe + "_rang", f["rang_indice"], "rang de l'indice de risque (1 = plus fort)",
                   "observe", s_i, PERIODE, format="entier")
    reg.ajouter(prefixe + "_sur", n, "nombre de zones classées", "observe", s_i, PERIODE,
                format="entier")
    reg.ajouter_si(prefixe + "_indice", f["indice_risque"], "indice de risque", "observe", s_i,
                   PERIODE, unite=UNITE_RANG, decimales=2)
    reg.ajouter_si(prefixe + "_alea", f["alea"], "composante aléa", "observe", tf.SOURCE_CHIRPS,
                   "1981-2023", unite=UNITE_RANG, decimales=2)
    reg.ajouter_si(prefixe + "_exposition", f["exposition"], "composante exposition", "observe",
                   s_p, "2023", unite=UNITE_RANG, decimales=2)
    reg.ajouter_si(prefixe + "_vulnerabilite", f["vulnerabilite_provisoire"],
                   "composante vulnérabilité (provisoire)", "observe", tf.SOURCE_EHCVM,
                   "2021-2023", unite=UNITE_RANG, decimales=2)
    forte, faible = _dominante(r), _dominante(r, plus_faible=True)
    if forte:
        reg.ajouter(prefixe + "_dominante", LIBELLES_COMPOSANTE[forte],
                    "composante la plus forte", "observe", s_i, PERIODE, format="texte")
    if faible:
        reg.ajouter(prefixe + "_faible", LIBELLES_COMPOSANTE[faible],
                    "composante la plus faible", "observe", s_i, PERIODE, format="texte")
    reg.ajouter_si(prefixe + "_pop2023", b["population_2023"], "population 2023", "observe", s_p,
                   "2023", format="entier", suffixe=" habitants")
    reg.ajouter_si(prefixe + "_pop2013", b["population_2013"], "population 2013", "observe",
                   "ANSD RGPH 2013", "2013", format="entier", suffixe=" habitants")
    reg.ajouter_si(prefixe + "_croissance", b["croissance_2013_2023_pct"],
                   "croissance démographique 2013-2023", "observe", s_p, "2013-2023",
                   format="pct", decimales=1)
    reg.ajouter_si(prefixe + "_densite", b["densite_2023_hab_km2"], "densité 2023", "observe",
                   s_p, "2023", format="entier", suffixe=" hab/km²")
    reg.ajouter_si(prefixe + "_pauvrete_region", b["taux_pauvrete_region_pct"],
                   "taux de pauvreté de la région", "observe", tf.SOURCE_EHCVM, "2021-2022",
                   format="pct", decimales=1)
    reg.ajouter_si(prefixe + "_jours_2sigma", b["jours_par_an_anomalie_sup_2sigma"],
                   "jours par an d'anomalie de pluie supérieure à 2 écarts-types (mai-octobre)",
                   "observe", tf.SOURCE_CHIRPS, "1981-2023", decimales=1,
                   suffixe=" jours/an")
    reg.ajouter_si(prefixe + "_jours_50mm", b["jours_par_an_pluie_sup_50mm"],
                   "jours par an de pluie supérieure à 50 mm (mai-octobre)", "observe",
                   tf.SOURCE_CHIRPS, "1981-2023", decimales=1, suffixe=" jours/an")
    return f


def _faits_fiabilite(c, v):
    fia = outil_vul._fiabilite(v, "departements") or {}
    val = fia.get("validation_inondations_documentees")
    reg = c.registre
    if isinstance(val, dict):
        reg.ajouter_si("auc_validation", val.get("auc_departements_touches_au_moins_une_fois"),
                       "AUC de l'indice face aux départements inondés (0,5 = hasard)", "observe",
                       tf.SOURCES["INONDATIONS"], "2005-2020", decimales=2)
        reg.ajouter_si("auc_exposition", (val.get("auc_par_composante") or {}).get(
            "exposition_seule"), "AUC de l'exposition seule face aux départements inondés",
            "observe", tf.SOURCES["INONDATIONS"], "2005-2020", decimales=2)
        reg.ajouter_si("n_dep_inondes", val.get("n_touches"),
                       "départements touchés par une inondation documentée", "observe",
                       tf.SOURCES["INONDATIONS"], "2005-2020", format="entier")
    sens = fia.get("sensibilite_aux_poids") or {}
    reg.ajouter_si("spearman_min_variantes", sens.get("spearman_avec_indice_publie_min"),
                   "corrélation de rang minimale entre l'indice et ses variantes de pondération",
                   "methode", "Analyse de sensibilité (script 29)", "2023", decimales=2)
    communs = sens.get("zones_du_top10_communes_a_toutes_les_variantes")
    if communs:
        reg.ajouter("top10_stable", ", ".join(communs),
                    "départements du top 10 quelle que soit la pondération", "methode",
                    "Analyse de sensibilité (script 29)", "2023", format="texte")


def _faits_ehcvm(c, v, region):
    indic = outil_vul._indicateurs_region(v, region) or {}
    libelles = {
        "wc_chasse_eau_pct": "ménages avec WC à chasse d'eau (région)",
        "fosse_rudimentaire_trou_ouvert_pct": "ménages avec fosse rudimentaire ou trou ouvert (région)",
        "acces_electricite_menages_pct": "ménages ayant accès à l'électricité (région)",
        "insecurite_alimentaire_moderee_ou_grave_pct": "insécurité alimentaire modérée ou grave (région)",
        "menages_ayant_subi_un_choc_3_ans_pct": "ménages ayant subi un choc en 3 ans (région)",
    }
    lignes = []
    for cle, lib in libelles.items():
        if indic.get(cle) is not None:
            c.registre.ajouter("ehcvm_" + cle, indic[cle], lib, "observe", tf.SOURCE_EHCVM,
                               "2021-2022", format="pct", decimales=1)
            lignes.append([lib[0].upper() + lib[1:], cellule(indic[cle], 1, " %")])
    if lignes:
        c.visuels.append(("analyse", tableau(
            ["Indicateur", "Valeur"], lignes,
            "Conditions de vie des ménages de la région de %s" % region,
            "Indicateurs de l'enquête EHCVM, connus à l'échelle de la région seulement : "
            "même valeur pour toutes les zones de la région.",
            "% des ménages", "2021-2022", tf.SOURCES["EHCVM"], statut="observe")))


def _carte(niveau, zone=None, surligne=None, composante="indice"):
    params = {"type": "vulnerabilite", "level": niveau, "component": composante}
    if zone:
        params["zone"] = zone
    spec, resume = outil_cartes.construire(params, {})
    if surligne is not None:
        spec["donnees"]["surligne"] = list(surligne)[:12]
    return spec


def _figure_carte(c, niveau, legende, zone=None, surligne=None):
    spec = _carte(niveau, zone, surligne)
    c.visuels.append(("analyse", figure(
        spec, "Indice de risque de pluies extrêmes par %s" % (
            "département" if niveau == "departements" else "arrondissement"),
        legende, UNITE_RANG, PERIODE, tf.SOURCE_INDICE, statut="observe")))


def _figure_decomposition(c, r, nom):
    valeurs = [fini(r["A_alea"]), fini(r["E_exposition"]), fini(r["V_vulnerabilite"]),
               fini(r["indice_risque"])]
    spec = {"genre": "barres", "hauteur_pouces": 1.9,
            "donnees": {"categories": ["Aléa", "Exposition", "Vulnérabilité (prov.)", "Indice"],
                        "valeurs": [round(x, 3) if x is not None else 0 for x in valeurs],
                        "x_label": "", "y_label": "rang centile", "horizontal": True,
                        "decimales": 2, "virgule": True}}
    c.visuels.append(("analyse", figure(
        spec, "Décomposition de l'indice : %s" % nom,
        "Valeur de chaque composante en rang centile : 1 = zone la plus exposée du pays pour "
        "cette composante. L'indice est la moyenne géométrique des trois.",
        UNITE_RANG, PERIODE, tf.SOURCE_INDICE, statut="observe")))


def _tableau_zones(c, t, titre, legende, niveau, max_lignes=15):
    t = t.sort_values("indice_risque", ascending=False).head(max_lignes)
    lignes = []
    for _, r in t.iterrows():
        f = outil_vul._fiche(r, niveau, 0)
        lignes.append([cellule(f["rang_indice"], 0), f["nom"], r["region"],
                       cellule(f["indice_risque"]), cellule(f["alea"]), cellule(f["exposition"]),
                       cellule(f["vulnerabilite_provisoire"]),
                       cellule(f["chiffres_bruts"]["population_2023"], 0)])
    c.visuels.append(("analyse", tableau(
        ["Rang", "Zone", "Région", "Indice", "Aléa", "Exposition", "Vulnérab. (prov.)",
         "Population 2023"], lignes, titre, legende,
        "rang centile (population : habitants)", PERIODE, tf.SOURCE_INDICE, statut="observe")))


def _tableau_communes(c, communes, titre):
    communes = sorted([l for l in communes if l.population_2023], key=lambda l: -l.population_2023)
    if not communes:
        return
    lignes = [[l.nom, l.arrondissement, cellule(l.population_2023, 0)] for l in communes[:20]]
    legende = "Communes classées par population 2023"
    if len(communes) > 20:
        legende += " (20 plus peuplées sur %d)" % len(communes)
    c.visuels.append(("analyse", tableau(
        ["Commune", "Arrondissement", "Population 2023"], lignes, titre,
        legende + ". L'indice de risque n'est pas calculé à l'échelle communale.",
        "habitants", "2023", tf.SOURCES["RGPH5"], statut="observe")))


def _recommandations(c, dominante_col, rang, sur, region):
    recos = []
    if dominante_col in RECO_DOMINANTE:
        recos.append(RECO_DOMINANTE[dominante_col])
    if normalise(region) == "dakar":
        recos.append(RECO_DAKAR)
    recos.append(RECO_TOUJOURS)
    c.recommandations = recos


def _dominante(r, plus_faible=False):
    cols = ("A_alea", "E_exposition", "V_vulnerabilite")
    vals = {k: fini(r[k]) for k in cols}
    vals = {k: x for k, x in vals.items() if x is not None}
    if not vals:
        return None
    return (min if plus_faible else max)(vals, key=vals.get)


def collecter(spec, data, gazetteer=None):
    v = data["vulnerabilite"]
    dep = _table(v, "departements")
    arr = v.get("arrondissements")
    arr = _table(v, "arrondissements") if arr is not None else None
    lieu = spec.lieu
    c = Collecte(registre=None, titre="", sous_titre="", zone=lieu.libelle(), periode=PERIODE)
    from ..faits import RegistreFaits
    c.registre = RegistreFaits()
    reg = c.registre
    c.sources = ["CHIRPS", "RGPH5", "RGPH2013", "EHCVM", "OCHA", "INONDATIONS"]
    c.limite("vulnerabilite_provisoire", "validation_indice", "resolution", "donnees_absentes",
             "couverture_chirps", "modules_en_developpement")
    c.mentions.append(Encadre(tf.AVERTISSEMENT_INDICE, "avertissement", "Lecture de l'indice"))
    reg.ajouter("n_departements", len(dep), "départements classés", "observe", tf.SOURCE_INDICE,
                PERIODE, format="entier")
    if arr is not None:
        reg.ajouter("n_arrondissements", int(arr["indice_risque"].notna().sum()),
                    "arrondissements classés", "observe", tf.SOURCE_INDICE, PERIODE,
                    format="entier")
    _faits_fiabilite(c, v)
    public = tf.PUBLICS[spec.public]
    c.titre = "Risque de pluies extrêmes et vulnérabilité"
    c.paragraphe("contexte",
                 "Ce rapport présente l'indice de risque de pluies extrêmes pour %s, établi "
                 "par la plateforme CLIMAT-SEN à l'intention des %s. Il situe la zone par "
                 "rapport au reste du pays et décompose son risque en aléa (fréquence des "
                 "pluies extrêmes), exposition (population) et vulnérabilité des ménages."
                 % (lieu.avec_article(), public))

    if lieu.niveau == "pays":
        c.sous_titre = "Classement national des départements et arrondissements"
        t = dep.sort_values("indice_risque", ascending=False)
        premier = t.iloc[0]
        reg.ajouter("top1_nom", premier["nom"], "département au premier rang", "observe",
                    tf.SOURCE_INDICE, PERIODE, format="texte")
        reg.ajouter("top1_indice", premier["indice_risque"], "indice du premier département",
                    "observe", tf.SOURCE_INDICE, PERIODE, unite=UNITE_RANG)
        reg.ajouter("top1_region", premier["region"], "région du premier département", "observe",
                    tf.SOURCE_INDICE, PERIODE, format="texte")
        top5 = ", ".join(t.head(5)["nom"])
        reg.ajouter("top5_noms", top5, "cinq premiers départements", "observe", tf.SOURCE_INDICE,
                    PERIODE, format="texte")
        dernier = t.iloc[-1]
        reg.ajouter("dernier_nom", dernier["nom"], "département au dernier rang", "observe",
                    tf.SOURCE_INDICE, PERIODE, format="texte")
        pop = (v.get("resume") or {}).get("population_2023_totale")
        reg.ajouter_si("pop_totale", pop, "population totale 2023", "observe", tf.SOURCE_RGPH5,
                       "2023", format="entier", suffixe=" habitants")
        n_sud_est = int(t.head(10)["region"].isin(
            ["Kolda", "Tambacounda", "Sédhiou", "Kédougou", "Ziguinchor"]).sum())
        reg.ajouter("top10_sud_est", n_sud_est,
                    "départements du top 10 situés dans le sud et l'est (Kolda, Tambacounda, "
                    "Sédhiou, Kédougou, Ziguinchor)", "observe", tf.SOURCE_INDICE, PERIODE,
                    format="entier")
        c.paragraphe("resume", "Sur les {{fait:n_departements}} départements classés, "
                     "{{fait:top1_nom}} (région de {{fait:top1_region}}) arrive en tête avec un "
                     "indice de {{fait:top1_indice}}. Les cinq premiers sont {{fait:top5_noms}} ; "
                     "{{fait:top10_sud_est}} des dix premiers se trouvent dans le sud et l'est du "
                     "pays, où l'aléa et la vulnérabilité des ménages se cumulent.", "observe")
        c.paragraphe("resume", "L'indice classe les zones entre elles ; il ne prédit pas les "
                     "inondations : face aux inondations documentées de 2005 à 2020, son score "
                     "de validation est de {{fait:auc_validation}} (0,5 = hasard).", "observe")
        c.paragraphe("analyse", "Le classement est stable vis-à-vis des pondérations : "
                     "{{fait:top10_stable}} restent dans les dix premiers quelle que soit la "
                     "variante testée.", "methode")
        c.paragraphe("analyse", "Les zones de la région de Dakar sont classées en bas du "
                     "classement ({{fait:dernier_nom}} est dernier) parce que la pauvreté "
                     "régionale y est la plus faible, alors que leur exposition est la plus forte "
                     "du pays.", "observe")
        _figure_carte(c, "departements", "Indice de risque des 46 départements ; les numéros "
                      "indiquent les 5 premiers rangs. Encart : presqu'île de Dakar.")
        _tableau_zones(c, dep, "Les quinze départements au plus fort indice de risque",
                       "Classement national par indice décroissant.", "departements")
        if arr is not None:
            _figure_carte(c, "arrondissements", "Indice de risque des arrondissements ; les "
                          "numéros indiquent les 5 premiers rangs.")
        c.paragraphe("conclusions", "Les priorités nationales se concentrent sur les "
                     "départements du sud et de l'est ({{fait:top5_noms}}), où un aléa élevé "
                     "se combine à une forte vulnérabilité des ménages.", "observe")
        c.recommandations = [
            "Concentrer la préparation pré-saison (curage, prépositionnement, information) sur "
            "les départements du haut du classement, en commençant par {{fait:top5_noms}}.",
            RECO_DAKAR, RECO_TOUJOURS]
        c.limite("biais_dakar")
        return c

    if lieu.niveau == "region":
        c.sous_titre = "Région de %s" % lieu.nom
        sous = dep[dep["region"].map(normalise) == normalise(lieu.nom)]
        if sous.empty:
            raise CollecteImpossible("Aucun département trouvé pour la région %s." % lieu.nom)
        meilleur = sous.sort_values("indice_risque", ascending=False).iloc[0]
        f = _fiche_faits(c, meilleur, "departements", len(dep))
        reg.ajouter("region_nom", lieu.nom, "région", "observe", tf.SOURCE_RGPH5, "2023",
                    format="texte")
        reg.ajouter("region_n_dep", len(sous), "départements de la région", "observe",
                    tf.SOURCE_INDICE, PERIODE, format="entier")
        reg.ajouter("region_pop2023", float(sous["population_2023"].sum()),
                    "population 2023 de la région", "observe", tf.SOURCE_RGPH5, "2023",
                    format="entier", suffixe=" habitants")
        c.paragraphe("resume", "La région de {{fait:region_nom}} compte {{fait:region_n_dep}} "
                     "départements et {{fait:region_pop2023}}. Le mieux classé, "
                     "{{fait:zone_nom}}, occupe le rang {{fait:zone_rang}} sur {{fait:zone_sur}} "
                     "au niveau national, avec un indice de {{fait:zone_indice}} ; sa "
                     "composante dominante est {{fait:zone_dominante}}.", "observe")
        c.paragraphe("analyse", "Dans {{fait:zone_nom}}, l'aléa vaut {{fait:zone_alea}}, "
                     "l'exposition {{fait:zone_exposition}} et la vulnérabilité "
                     "{{fait:zone_vulnerabilite}} (rangs centiles). On y compte en moyenne "
                     "{{fait:zone_jours_2sigma}} d'anomalie de pluie supérieure à 2 écarts-types "
                     "et {{fait:zone_jours_50mm}} de pluie supérieure à 50 mm.", "observe")
        pcodes = list(sous["pcode"])
        _figure_carte(c, "departements", "Indice de risque des départements ; les départements "
                      "de la région de %s sont mis en évidence." % lieu.nom, surligne=pcodes)
        _tableau_zones(c, sous, "Départements de la région de %s" % lieu.nom,
                       "Rang national (sur 46) et composantes de l'indice.", "departements")
        if arr is not None:
            sous_arr = arr[arr["region"].map(normalise) == normalise(lieu.nom)]
            if not sous_arr.empty:
                _tableau_zones(c, sous_arr, "Arrondissements de la région de %s" % lieu.nom,
                               "Rang national (sur 125) et composantes de l'indice.",
                               "arrondissements")
        _faits_ehcvm(c, v, lieu.nom)
        c.paragraphe("conclusions", "Au sein de la région, {{fait:zone_nom}} ressort en "
                     "priorité, principalement par {{fait:zone_dominante}}.", "observe")
        _recommandations(c, _dominante(meilleur), f["rang_indice"], len(dep), lieu.nom)
        if normalise(lieu.nom) == "dakar":
            c.limite("biais_dakar")
        return c

    # departement, arrondissement ou commune
    if lieu.niveau == "departement":
        niveau, t, code = "departements", dep, lieu.code
    else:
        if arr is None:
            raise CollecteImpossible("L'indice par arrondissement n'a pas été calculé.")
        niveau, t = "arrondissements", arr
        code = lieu.pcode_arrondissement if lieu.niveau == "commune" else lieu.code
    ligne = t[t["pcode"] == code]
    if ligne.empty or fini(ligne.iloc[0]["indice_risque"]) is None:
        raise CollecteImpossible("L'indice de risque n'est pas disponible pour %s."
                                 % lieu.libelle())
    r = ligne.iloc[0]
    n = int(t["indice_risque"].notna().sum())
    f = _fiche_faits(c, r, niveau, n)
    region = r["region"]
    reg.ajouter("zone_region", region, "région", "observe", tf.SOURCE_RGPH5, "2023",
                format="texte")
    echelle = "départements" if niveau == "departements" else "arrondissements"
    reg.ajouter("zone_echelle", echelle, "échelle de calcul de l'indice", "methode",
                tf.SOURCE_INDICE, PERIODE, format="texte")
    c.sous_titre = lieu.libelle()[0].upper() + lieu.libelle()[1:]

    if lieu.niveau == "commune":
        c.limite("echelle_arrondissement")
        reg.ajouter("commune_nom", lieu.nom, "commune demandée", "observe", tf.SOURCE_RGPH5,
                    "2023", format="texte")
        reg.ajouter_si("commune_pop2023", lieu.population_2023, "population 2023 de la commune",
                       "observe", tf.SOURCE_RGPH5, "2023", format="entier",
                       suffixe=" habitants")
        c.paragraphe("resume", "La commune de {{fait:commune_nom}} ({{fait:commune_pop2023}}) "
                     "appartient à l'arrondissement de {{fait:zone_nom}}, qui porte l'indice "
                     "de risque utilisé ici : l'indice n'est pas calculé à l'échelle "
                     "communale.", "observe")

    c.paragraphe("resume", "{{fait:zone_nom}} occupe le rang {{fait:zone_rang}} sur "
                 "{{fait:zone_sur}} {{fait:zone_echelle}}, avec un indice de "
                 "risque de {{fait:zone_indice}}. La composante la plus forte est "
                 "{{fait:zone_dominante}}, la plus faible {{fait:zone_faible}}. La zone compte "
                 "{{fait:zone_pop2023}} en 2023.", "observe")
    c.paragraphe("resume", "Ce rang compare les zones entre elles : il ne prédit ni la "
                 "survenue ni l'ampleur d'une inondation.", None)
    c.paragraphe("analyse", "Aléa. On y compte en moyenne {{fait:zone_jours_2sigma}} "
                 "d'anomalie de pluie supérieure à 2 écarts-types et {{fait:zone_jours_50mm}} de "
                 "pluie supérieure à 50 mm entre mai et octobre (1981-2023), soit un rang centile "
                 "de {{fait:zone_alea}}.", "observe")
    c.paragraphe("analyse", "Exposition. La population est passée de {{fait:zone_pop2013}} en "
                 "2013 à {{fait:zone_pop2023}} en 2023 ({{fait:zone_croissance}}), pour une "
                 "densité de {{fait:zone_densite}} : rang centile {{fait:zone_exposition}}.",
                 "observe")
    c.paragraphe("analyse", "Vulnérabilité (provisoire). Le taux de pauvreté de la région est "
                 "de {{fait:zone_pauvrete_region}} : rang centile {{fait:zone_vulnerabilite}}. "
                 "Cette composante est connue à l'échelle régionale seulement.", "observe")
    _figure_decomposition(c, r, f["nom"])
    if niveau == "departements":
        _figure_carte(c, "departements", "Indice de risque des 46 départements ; %s est mis en "
                      "évidence." % f["nom"], surligne=[r["pcode"]])
        if arr is not None:
            sous_arr = arr[arr["departement"].map(normalise) == normalise(f["nom"])]
            if not sous_arr.empty:
                _tableau_zones(c, sous_arr, "Arrondissements du département de %s" % f["nom"],
                               "Rang national (sur 125) et composantes de l'indice.",
                               "arrondissements")
                _figure_carte(c, "arrondissements", "Indice de risque des arrondissements ; "
                              "ceux du département de %s sont mis en évidence." % f["nom"],
                              surligne=list(sous_arr["pcode"]))
        if gazetteer is not None:
            _tableau_communes(c, gazetteer.communes_de(pcode_departement=r["pcode"]),
                              "Communes du département de %s" % f["nom"])
    else:
        reg.ajouter_si("dep_indice", r.get("indice_departement"),
                       "indice du département d'appartenance", "observe", tf.SOURCE_INDICE,
                       PERIODE, unite=UNITE_RANG)
        reg.ajouter_si("dep_rang", r.get("rang_departement"),
                       "rang du département d'appartenance (sur 46)", "observe",
                       tf.SOURCE_INDICE, PERIODE, format="entier")
        reg.ajouter("dep_nom", r["departement"], "département d'appartenance", "observe",
                    tf.SOURCE_RGPH5, "2023", format="texte")
        if "dep_rang" in reg:
            c.paragraphe("analyse", "Le département de {{fait:dep_nom}}, auquel appartient "
                         "la zone, occupe le rang {{fait:dep_rang}} sur 46 (indice "
                         "{{fait:dep_indice}}).", "observe")
        _figure_carte(c, "arrondissements", "Indice de risque des arrondissements ; %s est mis "
                      "en évidence." % f["nom"], surligne=[r["pcode"]])
        if gazetteer is not None:
            _tableau_communes(c, gazetteer.communes_de(pcode_arrondissement=r["pcode"]),
                              "Communes de l'arrondissement de %s" % f["nom"])
    if str(r.get("methode_alea", "")).startswith("pixel terrestre"):
        c.limites_specifiques.append(
            "La zone est plus petite qu'un pixel CHIRPS : son aléa est celui du pixel terrestre "
            "le plus proche, partagé avec les zones voisines.")
    _faits_ehcvm(c, v, region)
    if normalise(region) == "dakar":
        c.limite("biais_dakar")
        c.consignes.append("Zone de la region de Dakar: expliquer que le rang bas vient de la "
                           "pauvrete regionale la plus faible et ne signifie pas une absence de "
                           "risque d'inondation urbaine.")
    c.paragraphe("conclusions", "{{fait:zone_nom}} se situe %s (rang {{fait:zone_rang}} sur "
                 "{{fait:zone_sur}}). Son risque est porté d'abord par "
                 "{{fait:zone_dominante}}." % _palier(f["rang_indice"] or n, n), "observe")
    _recommandations(c, _dominante(r), f["rang_indice"], n, region)
    return c
