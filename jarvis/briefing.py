# -*- coding: utf-8 -*-
"""Briefing vocal du bulletin de veille pre-saison.

Meme mecanique que le mode soutenance (jarvis/soutenance.py): pour chaque
etape, le serveur compose page a ouvrir, carte a afficher et narration, et le
widget les joue en plein ecran, a voix haute, en enchainant seul.

Toute la narration est composee par le CODE a partir du bulletin JSON, du
carnet de fiabilite et des cartes: aucun modele, donc aucun chiffre invente
devant un decideur. Une etape sans donnees (etat oceanique pas encore
observe...) dit pourquoi et passe a la suite.
"""
import logging

from .tools import cartes as outil_cartes
from .tools import common  # noqa: F401  (chemin du paquet veille)

log = logging.getLogger("jarvis.briefing")

CONSEILS = {
    "faible": "maintenir la vigilance habituelle, car des pluies intenses locales restent possibles",
    "normal": "garder la vigilance habituelle de saison : curage des caniveaux et plans de contingence à jour",
    "eleve": "renforcer la préparation : curage des ouvrages, prépositionnement des moyens, information des quartiers exposés",
    "tres_eleve": "engager une préparation renforcée dès mai-juin",
    "indetermine": "suivre les bulletins officiels de l'ANACIM",
}


def fr(v, decimales=2):
    if v is None:
        return "n.d."
    return (("%%.%df" % decimales) % float(v)).replace(".", ",")


def pct(p):
    return "n.d." if p is None else "%d pour cent" % round(100 * p)


def _bulletin(annee):
    from veille import production
    dispo = production.bulletins_disponibles()
    if not dispo:
        return None
    annee = dispo[0] if annee is None else int(annee)
    return production.lire_bulletin(annee)


def _deposer(figures, sid, spec, carte=True):
    fig = figures.deposer(sid, spec)
    return {"id": fig.id, "titre": spec.get("titre", ""),
            "sous_titre": spec.get("sous_titre", ""), "carte": carte}


def _page(b):
    return {"page": "Veille", "filtres": {"saison": b["annee"]}}


def _sans_projection(b):
    avert = [a for a in b.get("avertissements") or [] if "océanique" in a]
    raison = avert[0] if avert else "l'état océanique de cette saison n'est pas disponible."
    return ("Cette étape n'est pas encore possible pour la saison %d : %s"
            % (b["annee"], raison.rstrip(".") + "."))


# =============================================================================
# Etapes
# =============================================================================
def _verdict(b, figures, sid):
    n = b["niveau_risque"]
    from veille.bulletin import presentation
    if presentation(n)["mode"] == "probabilite":
        texte = ("Bulletin de veille pour la saison des pluies %d. La prévision saisonnière "
                 "Copernicus, calibrée sur nos données de pluie, donne une probabilité "
                 "indicative d'année extrême de %s, quand une saison sur trois l'est en "
                 "moyenne. Sa compétence n'est pas démontrée : aucun niveau de risque n'est "
                 "annoncé." % (b["annee"], pct(n["probabilite_annee_extreme"])))
    elif n["code"] == "indetermine":
        texte = ("Bulletin de veille pour la saison des pluies %d. Le niveau de risque "
                 "n'est pas déterminé : la prévision saisonnière officielle de Copernicus "
                 "n'est pas encore disponible pour cette saison." % b["annee"])
    else:
        texte = ("Bulletin de veille pour la saison des pluies %d. Le risque d'une année "
                 "extrême est %s : %s, quand une saison sur trois l'est en moyenne. Ce "
                 "niveau vient de la prévision saisonnière Copernicus, calibrée sur nos "
                 "données de pluie. La confiance est %s." % (
                     b["annee"], n["libelle"].lower(), pct(n["probabilite_annee_extreme"]),
                     n["confiance"]))
    return dict(_page(b), figure=None, narration=texte)


def _ocean(b, figures, sid):
    if not b.get("projection"):
        return dict(_page(b), figure=None, narration=_sans_projection(b))
    spec, r = outil_cartes.construire({"type": "etat_oceanique", "year": b["annee"]}, {})
    lib = r["libelles_boites"]
    chaud, froid = r["boite_la_plus_chaude"], r["boite_la_plus_froide"]
    bo = r["anomalie_moyenne_par_boite_degC"]
    texte = ("Voici l'océan de novembre à avril, avant la saison. La zone la plus chaude "
             "est %s, à %s degré au-dessus de la normale ; la plus froide, %s, à %s degré. "
             "L'Atlantique tropical nord, voisin du Sénégal, est à %s degré." % (
                 lib[chaud], fr(bo[chaud], 1), lib[froid], fr(bo[froid], 1),
                 fr(bo.get("TNA"), 1)))
    return dict(_page(b), figure=_deposer(figures, sid, spec), narration=texte)


def _configuration(b, figures, sid):
    p = b.get("projection")
    if not p:
        return dict(_page(b), figure=None, narration=_sans_projection(b))
    c = p["configurations"][0]
    spec, _ = outil_cartes.construire({"type": "sst_cluster", "phase": "Toutes phases",
                                       "cluster": c["configuration"]}, {})
    annees = c.get("annees_principales") or []
    etat = c.get("etat_oceanique")
    if not etat:
        from veille import etats
        etat, _ = etats.etat_du_cluster(c["configuration"])
    texte = ("Parmi les neuf configurations océaniques identifiées dans le mémoire, celle "
             "qui ressemble le plus à cet océan est la configuration %d, avec une corrélation "
             "de %s%s. %s %d pour cent de ses événements extrêmes sont tombés lors d'années "
             "extrêmes." % (
                 c["configuration"], fr(c["correlation"]),
                 (" : une variante de l'état %s du Pacifique" % etat) if etat and etat != "mixte" else "",
                 ("On la retrouve surtout en %s." % ", ".join(str(a) for a in annees[:3]))
                 if annees else "", round(100 * c.get("part_evenements_en_annee_extreme", 0))))
    return dict(_page(b), figure=_deposer(figures, sid, spec), narration=texte)


def _trajectoire(b, figures, sid):
    p = b.get("projection")
    traj = (p or {}).get("trajectoire") or []
    if len(traj) < 2:
        return dict(_page(b), figure=None, narration=_sans_projection(b) if not p else
                    "Un seul mois observé : pas encore d'évolution à décrire.")
    debut, fin = traj[0], traj[-1]
    configs = []
    for t in traj:
        if not configs or configs[-1] != t["configuration"]:
            configs.append(t["configuration"])
    if len(configs) == 1:
        evol = ("L'océan est resté dans la même configuration, la %d, de novembre à avril."
                % configs[0])
    else:
        evol = ("La configuration dominante a évolué : %s." %
                ", puis ".join("la %d" % k for k in configs))
    texte = ("Pendant la veille, la lecture de l'océan a évolué mois après mois. %s "
             "L'indication expérimentale est passée de %s à %s." % (
                 evol, pct(debut["probabilite_experimentale"]),
                 pct(fin["probabilite_experimentale"])))
    return dict(_page(b), figure=None, narration=texte)


def _analogues(b, figures, sid):
    p = b.get("projection")
    ana = (p or {}).get("analogues") or []
    if not ana:
        return dict(_page(b), figure=None, narration=_sans_projection(b))
    ext = [a for a in ana if a["extreme"]]
    inond = [a["annee"] for a in ana if a["inondation_documentee"]]
    texte = ("Les saisons passées dont l'océan ressemblait le plus sont %s. %d sur %d ont "
             "été des années extrêmes%s. Ce sont des ressemblances, pas une prévision." % (
                 ", ".join(str(a["annee"]) for a in ana), len(ext), len(ana),
                 (", dont %s, années d'inondations" % " et ".join(str(a) for a in inond))
                 if inond else ""))
    texte += " " + _familles(p.get("familles_extremes"))
    return dict(_page(b), figure=None, narration=texte.strip())


def _familles(fam):
    """Phrase parlee sur les familles d'oceans des saisons extremes ('' si rien)."""
    calc = [f for f in (fam or {}).get("familles") or [] if f.get("correlation") is not None]
    if not calc:
        return ""
    code = fam.get("plus_proche")
    if not code:
        return ("Les saisons extrêmes passées ont connu deux grands types d'océan ; celui de "
                "cette année ne ressemble nettement à aucun des deux.")
    f = next(f for f in calc if f["code"] == code)
    ans = [str(a) for a in f["membres_utilises"]]
    ans = ans[0] if len(ans) == 1 else ", ".join(ans[:-1]) + " et " + ans[-1]
    return ("Parmi les deux grands types d'océan des saisons extrêmes passées, celui-ci "
            "ressemble au type %s, celui de %s : %s. Là encore, c'est une ressemblance, "
            "pas une prévision." % (code, ans, f["nom"][0].lower() + f["nom"][1:]))


def _copernicus(b, figures, sid):
    c = b.get("c3s") or {}
    if not c.get("disponible"):
        texte = ("La prévision Copernicus n'est pas disponible pour cette saison. Elle est "
                 "publiée chaque mois ; celle d'avril est la référence du bulletin.")
    else:
        sens = ("au-dessus de" if c["anomalie_standardisee"] > 0.2 else
                "en dessous de" if c["anomalie_standardisee"] < -0.2 else "proche de")
        comp = c.get("competence") or {}
        texte = ("Le modèle européen ECMWF, émis en avril, prévoit pour juillet à septembre "
                 "une pluie %s la normale : %s pour cent de ses membres sont dans le tiers le "
                 "plus humide. Sur trente-six saisons de test, sa capacité à distinguer une "
                 "année extrême reste modeste : une AUC de %s, là où 0,5 est le hasard." % (
                     sens, round(100 * c["part_membres_au_dessus_normale"]),
                     fr(comp.get("auc"))))
    return dict(_page(b), figure=None, narration=texte)


def _fiabilite(b, figures, sid):
    from veille import fiabilite
    c = fiabilite.carnet()
    if not c.get("disponible"):
        return dict(_page(b), figure=None,
                    narration="Le carnet de fiabilité n'est pas encore disponible.")
    r = c["niveau_de_risque"]
    manquees = [x["annee"] for x in c["inondations_documentees"] if x["verdict"] == "manquée"]
    texte = ("Peut-on s'y fier ? Sur %d saisons testées de %d à %d, le système aurait "
             "détecté %d saisons extrêmes, en aurait manqué %d, et émis %d fausses alertes. "
             "%s Il faut donc lire ce bulletin comme une indication, pas comme une certitude." % (
                 c["n_saisons"], c["periode"][0], c["periode"][1], r["comptes"]["détection"],
                 r["comptes"]["manquée"], r["comptes"]["fausse alerte"],
                 ("Parmi les inondations manquées : %s." % ", ".join(str(a) for a in manquees))
                 if manquees else ""))
    return {"page": "Veille", "filtres": {"saison": b["annee"]}, "figure": None,
            "narration": texte}


def _retenir(b, figures, sid):
    n = b["niveau_risque"]
    texte = ("Ce qu'il faut retenir pour la saison %d : %s. Un risque faible n'exclut pas "
             "une pluie intense locale, et ce bulletin ne remplace pas les prévisions et "
             "alertes officielles de l'ANACIM." % (b["annee"], CONSEILS[n["code"]]))
    v = b.get("verification")
    if v:
        texte += (" Cette saison étant passée, voici la vérification : elle a été %s%s." % (
            "une année extrême" if v["extreme_observe"] else "une année normale",
            ", avec des inondations documentées" if v["inondation_documentee"] else ""))
    texte += " Je réponds à vos questions."
    return dict(_page(b), figure=None, narration=texte)


ETAPES = [
    ("Le verdict", _verdict),
    ("L'océan de novembre à avril", _ocean),
    ("La configuration du mémoire", _configuration),
    ("L'évolution pendant la veille", _trajectoire),
    ("Les saisons qui lui ressemblent", _analogues),
    ("La prévision Copernicus", _copernicus),
    ("Peut-on s'y fier ?", _fiabilite),
    ("Ce qu'il faut retenir", _retenir),
]


def plan(annee=None):
    b = _bulletin(annee)
    if b is None:
        return None
    return {"annee": b["annee"],
            "etapes": [{"numero": i + 1, "titre": t} for i, (t, _) in enumerate(ETAPES)]}


def etape(numero, annee, figures, session_id):
    """L'etape `numero` (1..n) du briefing de la saison `annee`, composee maintenant."""
    if not 1 <= numero <= len(ETAPES):
        return None
    b = _bulletin(annee)
    if b is None:
        return None
    titre, fabrique = ETAPES[numero - 1]
    try:
        contenu = fabrique(b, figures, session_id)
    except Exception:
        log.exception("Etape %d du briefing impossible.", numero)
        contenu = dict(_page(b), figure=None,
                       narration="Cette étape n'est pas disponible : passons à la suite.")
    contenu.update({"numero": numero, "total": len(ETAPES), "titre": titre,
                    "annee": b["annee"]})
    return contenu
