"""Bulletin de veille pre-saison, en rapport.

Source unique: le bulletin JSON produit hors ligne (veille/production), lu
par l'outil get_seasonal_outlook, avec la meme regle de presentation:

  - mode "niveau"      : niveau de risque annonce (C3S calibree, competence
                         demontree);
  - mode "probabilite" : probabilite indicative seulement, AUCUN niveau;
  - mode "indetermine" : prevision C3S pas encore publiee, on dit pourquoi.

Les zones prioritaires viennent de l'indice de risque (module
Vulnerabilite): le bulletin ne module pas l'indice, ce sont deux
informations distinctes, presentees cote a cote.
"""
from ...tools import cartes as outil_cartes
from ...tools import veille as outil_veille
from ...tools import vulnerabilite as outil_vul
from ...tools.common import normalise
from .. import textes_fixes as tf
from ..document import Encadre
from ..faits import RegistreFaits
from . import Collecte, CollecteImpossible, cellule, figure, fini, tableau

SRC = "Veille pré-saison ClimatSen"
CONSEILS = {
    "faible": "Maintenir la vigilance habituelle : un risque faible n'exclut pas des pluies "
              "intenses locales.",
    "normal": "Garder la préparation habituelle de saison : curage des caniveaux et plans de "
              "contingence à jour avant juin.",
    "eleve": "Renforcer la préparation : curage des ouvrages, prépositionnement des moyens et "
             "information des quartiers exposés dès mai.",
    "tres_eleve": "Engager une préparation renforcée dès mai-juin, en priorité dans les zones "
                  "listées dans ce bulletin.",
}
CONSEIL_SANS_NIVEAU = ("En l'absence de niveau de risque annoncé, maintenir la préparation "
                       "standard de saison (curage, plans de contingence, information) et suivre "
                       "les mises à jour du bulletin et les prévisions de l'ANACIM.")


def _zones_prioritaires(c, v, lieu, gazetteer):
    dep = v["departements"].copy()
    dep["nom"] = dep["departement"]
    arr = v.get("arrondissements")
    if lieu.niveau == "pays":
        t = dep.sort_values("indice_risque", ascending=False).head(10)
        c.visuels.append(("analyse", tableau(
            ["Rang", "Département", "Région", "Indice", "Composante dominante",
             "Population 2023"],
            [[cellule(r["rang"], 0), r["nom"], r["region"], cellule(r["indice_risque"]),
              outil_vul._fiche(r, "departements", 46)["composante_dominante"].split(" (")[0],
              cellule(r["population_2023"], 0)] for _, r in t.iterrows()],
            "Zones prioritaires : les dix départements au plus fort indice de risque",
            "Classement de l'indice de risque de pluies extrêmes (aléa × exposition × "
            "vulnérabilité) ; indépendant du niveau de risque de la saison.",
            "rang centile (population : habitants)", "aléa 1981-2023 ; population 2023",
            tf.SOURCE_INDICE, statut="observe")))
        c.registre.ajouter("zones_prio", ", ".join(t.head(5)["nom"]),
                           "cinq départements prioritaires (indice de risque)", "observe",
                           tf.SOURCE_INDICE, "1981-2023 / 2023", format="texte")
        return
    # Zone precise: ses arrondissements, puis ses communes par indice de leur arrondissement.
    if arr is None:
        return
    arr = arr.copy()
    if lieu.niveau == "region":
        sous = arr[arr["region"].map(normalise) == normalise(lieu.nom)]
    elif lieu.niveau == "departement":
        sous = arr[arr["adm2_pcode"] == lieu.code]
    else:
        sous = arr[arr["pcode"] == (lieu.pcode_arrondissement or lieu.code)]
    sous = sous[sous["indice_risque"].notna()].sort_values("indice_risque", ascending=False)
    if sous.empty:
        return
    c.registre.ajouter("zones_prio", ", ".join(sous.head(3)["arrondissement"]),
                       "arrondissements prioritaires de la zone", "observe", tf.SOURCE_INDICE,
                       "1981-2023 / 2023", format="texte")
    c.visuels.append(("analyse", tableau(
        ["Rang national", "Arrondissement", "Département", "Indice", "Population 2023"],
        [[cellule(r["rang"], 0), r["arrondissement"], r["departement"],
          cellule(r["indice_risque"]), cellule(r["population_2023"], 0)]
         for _, r in sous.head(12).iterrows()],
        "Arrondissements de la zone classés par indice de risque",
        "Rang sur les 125 arrondissements ; l'indice classe les zones entre elles.",
        "rang centile (population : habitants)", "aléa 1981-2023 ; population 2023",
        tf.SOURCE_INDICE, statut="observe")))
    if gazetteer is not None:
        indice = {r["pcode"]: r["indice_risque"] for _, r in sous.iterrows()}
        communes = [l for l in gazetteer.lieux if l.niveau == "commune"
                    and l.pcode_arrondissement in indice]
        communes.sort(key=lambda l: (-indice[l.pcode_arrondissement], -(l.population_2023 or 0)))
        if communes:
            c.visuels.append(("analyse", tableau(
                ["Commune", "Arrondissement", "Indice de l'arrondissement", "Population 2023"],
                [[l.nom, l.arrondissement, cellule(indice[l.pcode_arrondissement]),
                  cellule(l.population_2023, 0)] for l in communes[:20]],
                "Communes prioritaires de la zone",
                "Communes classées par l'indice de leur arrondissement, puis par population "
                "(l'indice n'est pas calculé à l'échelle communale)%s."
                % (" ; 20 premières sur %d" % len(communes) if len(communes) > 20 else ""),
                "rang centile ; habitants", "2023", tf.SOURCE_INDICE, statut="observe")))
            c.limite("echelle_arrondissement")


def collecter(spec, data, gazetteer=None):
    from veille import production
    if not production.bulletins_disponibles():
        raise CollecteImpossible("Aucun bulletin de veille n'a encore été produit.")
    b = outil_veille.run({"year": spec.saison}, {})
    saison = b["annee"]
    pres = b.get("presentation") or {}
    mode = pres.get("mode", "indetermine")
    n = b["niveau_risque"]
    reg = RegistreFaits()
    c = Collecte(registre=reg, titre="Bulletin de veille pré-saison",
                 sous_titre="Saison des pluies %d — %s" % (saison, spec.lieu.libelle()),
                 zone=spec.lieu.libelle(), periode="saison %d" % saison)
    c.sources = ["C3S", "OISST", "CHIRPS", "RGPH5", "EHCVM"]
    c.limite("competence_veille", "couverture_chirps", "modules_en_developpement",
             "vulnerabilite_provisoire", "resolution")
    c.mentions.append(Encadre(tf.MENTION_ANACIM, "officiel", "Alertes officielles"))
    c.mentions.append(Encadre(tf.AVERTISSEMENT_PROJECTION, "avertissement",
                              "Une projection n'est pas une certitude"))
    for a in b.get("avertissements") or []:
        c.limites_specifiques.append(a)

    reg.ajouter("saison", saison, "saison visée", "methode", SRC, "saison %d" % saison,
                format="annee")
    # Un bulletin calcule APRES sa saison (1998-2023, tous calcules d'un coup
    # le 27/09/2026) est une reconstitution: "a la date du 27 septembre 2026"
    # faisait croire a un bulletin emis ce jour-la pour une saison passee.
    retrospectif = saison < int(str(b["emis_le"])[:4])
    reg.ajouter("emis_le", b["emis_le"],
                "date de calcul du bulletin" if retrospectif else "date d'émission du bulletin",
                "methode", SRC, "saison %d" % saison, format="date")
    reg.ajouter("statut_bulletin", b["statut"], "statut du bulletin", "methode", SRC,
                "saison %d" % saison, format="texte")
    ctx = b.get("contexte") or {}
    reg.ajouter_si("freq_ref", ctx.get("base_climatologique"),
                   "fréquence de référence d'une année extrême", "observe", tf.SOURCE_CHIRPS,
                   "1981-2023", format="fraction_pct", decimales=0)
    fr_ = ctx.get("frequence_recente") or {}
    if fr_.get("sur"):
        reg.ajouter("freq_recente", "%d saisons extrêmes sur %d (%d-%d)" % (
            fr_["extremes"], fr_["sur"], fr_["annees"][0], fr_["annees"][1]),
            "fréquence récente des années extrêmes", "observe", tf.SOURCE_CHIRPS,
            "%d-%d" % tuple(fr_["annees"]), format="texte")
    c3s = b.get("c3s") or {}
    comp = c3s.get("competence") or {}
    reg.ajouter_si("c3s_auc", comp.get("auc"), "compétence mesurée de la prévision C3S (AUC, "
                   "0,5 = hasard)", "observe", tf.SOURCES["C3S"], "1981-2016", decimales=2)
    cp = b.get("competence_projection") or {}
    pr = cp.get("prevision_reelle") or {}
    reg.ajouter_si("proj_auc", pr.get("auc"), "compétence de la projection océanique en "
                   "prévision réelle (AUC, 0,5 = hasard)", "observe", SRC, "1998-2023",
                   decimales=2)

    public = tf.PUBLICS[spec.public]
    if retrospectif:
        c.paragraphe("contexte", "Ce bulletin est une reconstitution a posteriori : il "
                     "recalcule, avec la méthode actuelle de la veille, le risque que la saison "
                     "des pluies {{fait:saison}} soit une année de pluies extrêmes au Sénégal, "
                     "et les zones à préparer en priorité dans %s. Il ne reproduit pas un "
                     "bulletin réellement diffusé avant cette saison. Il s'adresse aux %s."
                     % (spec.lieu.avec_article(), public))
    else:
        c.paragraphe("contexte", "Ce bulletin fait le point, à la date du {{fait:emis_le}}, sur "
                     "le risque que la saison des pluies {{fait:saison}} soit une année de "
                     "pluies extrêmes au Sénégal, et sur les zones à préparer en priorité dans "
                     "%s. Il s'adresse aux %s." % (spec.lieu.avec_article(), public))

    # --- niveau, probabilite ou indetermine -------------------------------------
    if mode == "niveau" and n.get("probabilite_annee_extreme") is not None:
        reg.ajouter("niveau", n["libelle"], "niveau de risque annoncé", "projete", tf.SOURCES["C3S"],
                    "saison %d" % saison, format="texte")
        reg.ajouter("proba", n["probabilite_annee_extreme"], "probabilité d'année extrême",
                    "projete", tf.SOURCES["C3S"], "saison %d" % saison, format="fraction_pct",
                    decimales=0)
        reg.ajouter_si("confiance", n.get("confiance"), "confiance", "projete", tf.SOURCES["C3S"],
                       "saison %d" % saison, format="texte")
        c.paragraphe("resume", "Niveau de risque annoncé pour la saison {{fait:saison}} : "
                     "{{fait:niveau}}. La probabilité d'une année extrême est de "
                     "{{fait:proba}}, contre {{fait:freq_ref}} en moyenne, d'après la prévision "
                     "saisonnière Copernicus calibrée sur les pluies observées (confiance "
                     "{{fait:confiance}}).", "projete")
        conseil = CONSEILS.get(n["code"], CONSEIL_SANS_NIVEAU)
    elif mode == "probabilite" and n.get("probabilite_annee_extreme") is not None:
        reg.ajouter("proba", n["probabilite_annee_extreme"], "probabilité indicative d'année "
                    "extrême", "projete", tf.SOURCES["C3S"], "saison %d" % saison,
                    format="fraction_pct", decimales=0)
        c.paragraphe("resume", "Aucun niveau de risque n'est annoncé pour la saison "
                     "{{fait:saison}}. La prévision saisonnière Copernicus donne une "
                     "probabilité indicative d'année extrême de {{fait:proba}}, contre "
                     "{{fait:freq_ref}} en moyenne, mais sa compétence n'est pas démontrée "
                     "(score {{fait:c3s_auc}}, 0,5 = hasard).", "projete")
        conseil = CONSEIL_SANS_NIVEAU
    else:
        raison = pres.get("titre") or "prévision non disponible"
        reg.ajouter("raison_indetermine", raison[0].lower() + raison[1:],
                    "raison de l'absence de niveau", "methode", SRC, "saison %d" % saison,
                    format="texte")
        c.paragraphe("resume", "Aucun niveau de risque ne peut encore être annoncé pour la "
                     "saison {{fait:saison}} ({{fait:raison_indetermine}}) : la prévision "
                     "saisonnière Copernicus n'est pas encore publiée. En moyenne, "
                     "{{fait:freq_ref}} des saisons sont des années extrêmes.", "projete")
        conseil = CONSEIL_SANS_NIVEAU
    if "freq_recente" in reg:
        c.paragraphe("resume", "Contexte récent : {{fait:freq_recente}}.", "observe")

    # --- etat oceanique et projection experimentale ------------------------------
    proj = b.get("projection") or {}
    if proj:
        reg.ajouter_si("proj_proba", proj.get("probabilite_experimentale"),
                       "probabilité expérimentale de la projection océanique", "projete", SRC,
                       "saison %d" % saison, format="fraction_pct", decimales=0)
        confs = proj.get("configurations") or []
        if confs:
            reg.ajouter("proj_config", "C%d" % confs[0]["configuration"],
                        "configuration océanique la plus proche", "observe", SRC,
                        "novembre-avril", format="texte")
            reg.ajouter_si("proj_config_r", confs[0].get("correlation"),
                           "ressemblance avec cette configuration (corrélation de motif)",
                           "observe", SRC, "novembre-avril", decimales=2)
        ana = proj.get("analogues") or []
        if ana:
            reg.ajouter("analogues", ", ".join(str(a["annee"]) for a in ana[:3]),
                        "années analogues", "observe", SRC, "1983-2023", format="texte")
            c.visuels.append(("analyse", tableau(
                ["Année", "Ressemblance", "Année extrême", "Inondation documentée"],
                [[str(a["annee"]), cellule(a.get("correlation"), 2),
                  "oui" if a.get("extreme") else "non",
                  "oui" if a.get("inondation_documentee") else "non"] for a in ana[:5]],
                "Années dont l'océan ressemblait le plus",
                "Années analogues par la ressemblance de l'état océanique de novembre à avril ; "
                "une ressemblance décrit un passé, elle ne prévoit pas la saison.",
                "corrélation de motif (sans unité)", "1983-2023", tf.SOURCE_OISST,
                statut="observe")))
        c.paragraphe("analyse", "État océanique. De novembre à avril, l'océan ressemble le plus "
                     "à la configuration {{fait:proj_config}} (ressemblance "
                     "{{fait:proj_config_r}}) ; les années les plus proches sont "
                     "{{fait:analogues}}. La projection expérimentale qui en découle donne "
                     "{{fait:proj_proba}}, mais sa compétence en prévision réelle n'est pas "
                     "démontrée (score {{fait:proj_auc}}).", "projete")
        fam = proj.get("familles_extremes") or {}
        calc = [f for f in fam.get("familles") or [] if f.get("correlation") is not None]
        if calc:
            c.visuels.append(("analyse", tableau(
                ["Famille", "Saisons", "Signature", "Ressemblance"],
                [["%s · %s" % (f["code"], f["nom"]),
                  ", ".join(str(a) for a in f["membres_utilises"]),
                  f["signature"], cellule(f["correlation"], 2)] for f in calc],
                "Familles d'océans des saisons extrêmes",
                "Les saisons les plus extrêmes ne partagent pas un même océan : deux familles "
                "(La Niña et Atlantique frais ; océans chauds partout). Ressemblance "
                "descriptive, sans valeur de prévision démontrée.",
                "corrélation de motif (sans unité)", "1984-2023", tf.SOURCE_OISST,
                statut="observe")))
            plus = fam.get("plus_proche")
            reg.ajouter("famille_extreme",
                        ("famille %s (saisons %s)" % (plus, "/".join(
                            str(a) for a in next(f for f in calc if f["code"] == plus)
                            ["membres_utilises"]))) if plus else "aucune des deux familles",
                        "famille d'océans de saisons extrêmes la plus ressemblante", "observe",
                        SRC, "novembre-avril", format="texte")
            c.paragraphe("analyse", "Familles d'océans des saisons extrêmes. L'océan de "
                         "novembre à avril ressemble à : {{fait:famille_extreme}}. Cette "
                         "ressemblance décrit le passé ; testée, elle ne prévoit pas mieux que "
                         "le hasard la saison à venir.", "observe")
        try:
            spec_o, _ = outil_cartes.construire({"type": "etat_oceanique", "year": saison}, {})
            c.visuels.append(("analyse", figure(
                spec_o, "État de l'océan avant la saison %d" % saison,
                "Anomalie moyenne de température de surface de la mer de novembre à avril "
                "(60°S-60°N), écart à la climatologie.", "°C (anomalie)",
                "novembre %d - avril %d" % (saison - 1, saison), tf.SOURCE_OISST,
                statut="observe")))
        except Exception:
            c.limites_specifiques.append("La carte de l'état océanique n'a pas pu être produite.")
    else:
        c.paragraphe("analyse", "État océanique. L'état de l'océan de novembre à avril précédant "
                     "la saison n'est pas encore disponible : la projection océanique n'est donc "
                     "pas calculée.", "observe")

    ver = b.get("verification") or {}
    if ver.get("extreme_observe") is not None:
        reg.ajouter("verif_extreme", "oui" if ver["extreme_observe"] else "non",
                    "saison effectivement extrême", "observe", tf.SOURCE_CHIRPS,
                    "saison %d" % saison, format="texte")
        reg.ajouter_si("verif_rang", ver.get("rang"), "rang de la saison (1 = plus extrême)",
                       "observe", tf.SOURCE_CHIRPS, "1981-2023", format="entier")
        c.paragraphe("analyse", "Vérification. Saison passée : a-t-elle été extrême ? "
                     "{{fait:verif_extreme}} (rang {{fait:verif_rang}} des saisons "
                     "1981-2023).", "observe")

    # --- zones prioritaires ---------------------------------------------------------
    _zones_prioritaires(c, data["vulnerabilite"], spec.lieu, gazetteer)
    if "zones_prio" in reg:
        c.paragraphe("analyse", "Zones à préparer en priorité. Indépendamment du niveau de la "
                     "saison, l'indice de risque désigne en priorité : {{fait:zones_prio}}.",
                     "observe")
    c.paragraphe("conclusions", "Ce bulletin ne remplace pas les alertes de l'ANACIM ; il "
                 "aide à organiser la préparation avant la saison.", None)
    c.recommandations = [conseil]
    if "zones_prio" in reg:
        c.recommandations.append("Préparer en priorité {{fait:zones_prio}} : curage des "
                                 "ouvrages, information des habitants, sites d'accueil.")
    c.recommandations.append("Suivre les mises à jour du bulletin (premier bulletin début "
                             "décembre, bulletin final mi-avril) et les prévisions et alertes "
                             "de l'ANACIM pendant la saison.")
    if normalise(spec.lieu.region or spec.lieu.nom) == "dakar":
        c.limite("biais_dakar")
    c.consignes.append("Ne jamais annoncer de niveau de risque si le fait 'niveau' est absent.")
    return c
