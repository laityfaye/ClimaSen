# -*- coding: utf-8 -*-
"""Composition du bulletin de veille pre-saison.

Regles fixes, ecrites ici une fois pour toutes:

  NIVEAU DE RISQUE: calcule a partir de la probabilite d'annee extreme issue
  de C3S (la seule source evaluee en prevision reelle sur une longue periode,
  mais SANS competence demontree a ce jour: AUC LOYO 0,59, p = 0,19), par
  rapport a la frequence climatologique d'une annee extreme (1/3):
      p < 0,20        faible
      0,20 - 0,40     normal (proche de la climatologie)
      0,40 - 0,60     eleve
      p >= 0,60       tres eleve
  Sans C3S: niveau "indetermine". La projection oceanique ne fixe JAMAIS le
  niveau tant que sa competence en prevision reelle n'est pas demontree
  (projection.evaluer, cle utilisable_seule).

  CONFIANCE: "moyenne" si la calibration C3S est significative en LOYO
  (p < 0,05) avec un Brier skill score positif, "faible" sinon. Jamais
  "forte": 36 annees de retro-prevision ne le permettent pas.

  AFFICHAGE (presentation()): le niveau colore n'est MONTRE que si la
  competence est demontree (confiance "moyenne"). Sinon on affiche une
  probabilite indicative face a la reference de 33 %, avec la mention
  "competence non demontree". Le code du niveau reste calcule (carnet de
  fiabilite, archives), mais n'est pas presente comme une prevision.

Le texte de synthese est compose par le code a partir des chiffres, sans
modele de langage: rien ne peut y etre invente.
"""
import datetime as dt
import re

import numpy as np

from . import INONDATIONS_CONNUES
from . import annees as mod_annees
from . import familles as mod_familles

VERSION = 1

NIVEAUX = (
    (0.20, "faible", "Faible"),
    (0.40, "normal", "Normal"),
    (0.60, "eleve", "Élevé"),
    (1.01, "tres_eleve", "Très élevé"),
)
COULEURS = {"faible": "#10B981", "normal": "#0EA5E9", "eleve": "#F59E0B",
            "tres_eleve": "#EF4444", "indetermine": "#64748B"}
NOMS_MOIS = {1: "janvier", 2: "février", 3: "mars", 4: "avril", 11: "novembre", 12: "décembre"}


def niveau(p):
    if p is None:
        return "indetermine", "Indéterminé"
    for borne, code, libelle in NIVEAUX:
        if p < borne:
            return code, libelle
    return NIVEAUX[-1][1], NIVEAUX[-1][2]


def presentation(n):
    """Comment afficher niveau_risque (derive a la lecture: vaut aussi pour les
    bulletins archives). Renvoie {"mode", "titre", "valeur", "couleur", "note"}.

    mode "niveau": competence demontree, niveau colore.
    mode "probabilite": probabilite indicative, couleur neutre.
    mode "indetermine": aucune source.
    """
    p = n.get("probabilite_annee_extreme")
    if p is None or n.get("code") == "indetermine":
        return {"mode": "indetermine", "titre": "Pas encore de prévision",
                "valeur": "—", "couleur": COULEURS["indetermine"],
                "note": "en moyenne, 1 saison sur 3 est extrême"}
    src = "C3S" if n.get("source") == "c3s" else "projection océanique"
    if n.get("confiance") == "moyenne":
        return {"mode": "niveau", "titre": "Niveau de risque", "valeur": n["libelle"],
                "couleur": n["couleur"],
                "note": "probabilité %s (référence 33 %%) · %s · confiance moyenne" % (
                    _pct(p), src)}
    return {"mode": "probabilite", "titre": "Probabilité indicative d'année extrême",
            "valeur": _pct(p), "couleur": COULEURS["indetermine"],
            "note": "référence 33 %% · %s · compétence non démontrée" % src}


def confiance(competence):
    if not competence:
        return "faible"
    ok = competence.get("p_permutation", 1) < 0.05 and competence.get("brier_skill_score", -1) > 0
    return "moyenne" if ok else "faible"


def _fr(texte):
    """Decimales a la francaise dans le texte (0.17 -> 0,17); le JSON garde ses nombres."""
    return re.sub(r"(\d)\.(\d)", r"\1,\2", texte)


def verdict_fr(cp):
    """Verdict de competence de la projection, en francais."""
    if not cp:
        return ""
    if cp.get("utilisable_seule"):
        return "compétence démontrée en prévision réelle"
    lo = cp.get("loyo") or {}
    p = lo.get("p_permutation", 1)
    # Revue 27/09/2026 (V2): 4 variantes comparees -> p corrige (Bonferroni).
    pc = lo.get("p_corrige_variantes", min(1.0, 4 * p))
    if pc < 0.05:
        return ("signal physique présent (validation année exclue), mais pas de compétence "
                "démontrée en prévision réelle : indication expérimentale seulement")
    if p < 0.05:
        return ("signal suggestif en validation année exclue (p = %.3f, mais %.2f une fois "
                "corrigé pour les 4 variantes comparées) et pas de compétence démontrée en "
                "prévision réelle : indication expérimentale seulement" % (p, pc))
    return "pas de compétence démontrée"


def _pct(p):
    return "%d %%" % round(100 * p)


def frequence_recente(empreinte, annee, fenetre=10):
    """Annees extremes parmi les `fenetre` dernieres saisons observees avant `annee`."""
    s = mod_annees.seuil(empreinte)
    passees = [a for a in empreinte.index if a < annee][-fenetre:]
    n = int(sum(empreinte.loc[a] > s for a in passees))
    return {"annees": [int(passees[0]), int(passees[-1])] if passees else None,
            "extremes": n, "sur": len(passees)}


def composer(annee, projection=None, c3s=None, competence_projection=None,
             empreinte=None, etat_mois=None, etat_partiel=False, avertissements=None):
    """Assemble le bulletin (dict serialisable en JSON)."""
    empreinte = mod_annees.empreinte() if empreinte is None else empreinte
    avertissements = list(avertissements or [])
    table, s = mod_annees.classement(empreinte)
    base = 1 / 3

    # --- Niveau de risque -------------------------------------------------
    p_c3s = c3s.get("probabilite_annee_extreme") if c3s and c3s.get("disponible") else None
    utilisable = bool(competence_projection and competence_projection.get("utilisable_seule"))
    p_proj = projection.get("probabilite_experimentale") if projection else None
    if p_c3s is not None:
        p_niveau, source = p_c3s, "c3s"
        conf = confiance(c3s.get("competence"))
    elif utilisable and p_proj is not None:
        p_niveau, source = p_proj, "projection"
        conf = "faible"
    else:
        p_niveau, source, conf = None, "aucune", None
    code, libelle = niveau(p_niveau)
    if etat_partiel and source == "projection":
        conf = "faible"

    bulletin = {
        "version": VERSION,
        "annee": int(annee),
        "emis_le": dt.date.today().isoformat(),
        "statut": "provisoire" if etat_partiel else ("complet" if p_niveau is not None else "partiel"),
        "niveau_risque": {
            "code": code, "libelle": libelle, "couleur": COULEURS[code],
            "probabilite_annee_extreme": None if p_niveau is None else round(p_niveau, 3),
            "source": source, "confiance": conf,
            "regle": "faible < 20 % <= normal < 40 % <= élevé < 60 % <= très élevé "
                     "(fréquence climatologique d'une année extrême : 33 %)",
        },
        "definition": dict(mod_annees.verification_definition(empreinte),
                           mesure="empreinte saisonnière = somme de l'étendue (% du territoire) "
                                  "de tous les événements extrêmes CHIRPS (> 2 sigma) de la saison",
                           annee_extreme="empreinte dans le tiers supérieur des années"),
        "contexte": {"base_climatologique": round(base, 3),
                     "frequence_recente": frequence_recente(empreinte, annee)},
        "c3s": c3s or {"disponible": False, "raison": "non demandée"},
        "projection": projection,
        "competence_projection": _resume_competence(competence_projection),
        "avertissements": avertissements,
    }
    if etat_mois:
        bulletin["etat_oceanique_mois"] = etat_mois
    if annee in table.index:
        bulletin["verification"] = {
            "empreinte_observee": float(table.loc[annee, "empreinte"]),
            "rang": int(table.loc[annee, "rang"]),
            "extreme_observe": bool(table.loc[annee, "extreme"]),
            "inondation_documentee": annee in INONDATIONS_CONNUES,
            "seuil": round(s, 1),
        }
    bulletin["synthese"] = synthese(bulletin)
    return bulletin


def _resume_competence(comp):
    if not comp:
        return None
    garde = ("n", "annees_extremes", "auc", "p_permutation", "p_corrige_variantes",
             "brier_skill_score", "calculable")
    return {
        "loyo": {k: v for k, v in comp.get("loyo", {}).items() if k in garde},
        "prevision_reelle": {k: v for k, v in comp.get("prevision_reelle", {}).items() if k in garde},
        "verdict": verdict_fr(comp),
        "utilisable_seule": comp.get("utilisable_seule"),
        "methode": comp.get("methode"),
        "calcule_le": comp.get("calcule_le"),
    }


def synthese(b):
    """Texte du bulletin, compose a partir des seuls chiffres du bulletin."""
    phrases = []
    n = b["niveau_risque"]
    annee = b["annee"]
    pres = presentation(n)
    src = ("prévision saisonnière Copernicus C3S" if n["source"] == "c3s"
           else "projection de l'état océanique")
    if pres["mode"] == "indetermine":
        phrases.append("Saison %d : niveau de risque non déterminé, faute de prévision "
                       "saisonnière officielle (Copernicus C3S) disponible." % annee)
    elif pres["mode"] == "probabilite":
        phrases.append("Saison %d : probabilité indicative d'année extrême %s, contre %s en "
                       "moyenne, d'après la %s. Sa compétence n'est pas démontrée : aucun "
                       "niveau de risque n'est annoncé." % (
                           annee, _pct(n["probabilite_annee_extreme"]),
                           _pct(b["contexte"]["base_climatologique"]), src))
    else:
        phrases.append("Saison %d : risque d'année extrême %s (probabilité %s, contre %s en "
                       "moyenne), d'après la %s. Confiance %s." % (
                           annee, n["libelle"].lower(), _pct(n["probabilite_annee_extreme"]),
                           _pct(b["contexte"]["base_climatologique"]), src, n["confiance"]))
    c3s = b.get("c3s") or {}
    if c3s.get("disponible"):
        phrases.append("Le modèle %s prévoit pour juillet-septembre une pluie %s la normale "
                       "(anomalie %+.1f écart-type) ; %s des membres sont dans le tiers le plus "
                       "humide." % (c3s.get("centre", "").upper(),
                                    "au-dessus de" if c3s["anomalie_standardisee"] > 0.2 else
                                    "en dessous de" if c3s["anomalie_standardisee"] < -0.2 else
                                    "proche de",
                                    c3s["anomalie_standardisee"],
                                    _pct(c3s["part_membres_au_dessus_normale"])))
    p = b.get("projection")
    if p:
        conf = p.get("configurations") or []
        if conf:
            c = conf[0]
            etat = c.get("etat_oceanique")
            # Bulletin retrospectif: les annees principales posterieures a la
            # saison sont retirees; la liste peut alors etre vide.
            principales = c.get("annees_principales") or []
            phrases.append("De novembre à avril, l'océan ressemble surtout à la configuration C%d "
                           "du mémoire (corrélation %.2f)%s%s." % (
                               c["configuration"], c["correlation"],
                               (", une variante de l'état %s" % etat) if etat and etat != "mixte" else "",
                               (", celle des années %s" % ", ".join(str(a) for a in principales[:3]))
                               if principales else
                               ", dont les années principales sont toutes postérieures à la saison"))
        ana = p.get("analogues") or []
        if ana:
            ext = [a for a in ana if a["extreme"]]
            phrases.append("Années les plus ressemblantes : %s ; %d sur %d ont été des années "
                           "extrêmes%s." % (
                               ", ".join(str(a["annee"]) for a in ana), len(ext), len(ana),
                               " (dont %s, inondations documentées)" % ", ".join(
                                   str(a["annee"]) for a in ana if a["inondation_documentee"])
                               if any(a["inondation_documentee"] for a in ana) else ""))
        ph = mod_familles.phrase(p.get("familles_extremes"))
        if ph:
            phrases.append(ph)
        if p.get("probabilite_experimentale") is not None:
            cp = b.get("competence_projection") or {}
            pr = cp.get("prevision_reelle") or {}
            phrases.append("Indication expérimentale de la projection : %s. Cette méthode %s "
                           "(AUC %.2f en conditions réelles de prévision) ; elle ne fixe pas le "
                           "niveau de risque." % (
                               _pct(p["probabilite_experimentale"]),
                               "n'a pas de compétence démontrée en prévision réelle"
                               if not cp.get("utilisable_seule") else "a une compétence démontrée",
                               pr.get("auc", float("nan"))))
    fr = b["contexte"]["frequence_recente"]
    if fr and fr.get("sur"):
        phrases.append("Contexte : %d des %d dernières saisons observées (%d-%d) ont été extrêmes, "
                       "pour une fréquence de référence d'une sur trois." % (
                           fr["extremes"], fr["sur"], fr["annees"][0], fr["annees"][1]))
    v = b.get("verification")
    if v:
        phrases.append("Vérification : la saison %d a été %s (empreinte %.0f, rang %d)%s." % (
            annee, "extrême" if v["extreme_observe"] else "non extrême",
            v["empreinte_observee"], v["rang"],
            ", inondations documentées" if v["inondation_documentee"] else ""))
    return _fr(" ".join(phrases))


# =============================================================================
# Rendu Markdown (acteurs operationnels)
# =============================================================================
def markdown(b):
    n = b["niveau_risque"]
    lignes = [
        "# Bulletin de veille pré-saison — saison des pluies %d" % b["annee"],
        "",
        "*ClimatSen · émis le %s · statut : %s*" % (b["emis_le"], b["statut"]),
        "",
    ]
    pres = presentation(n)
    if pres["mode"] == "niveau":
        lignes += ["## Niveau de risque d'année extrême : **%s**" % n["libelle"].upper(), ""]
    elif pres["mode"] == "probabilite":
        lignes += ["## Probabilité indicative d'année extrême : **%s** (référence 33 %%)"
                   % pres["valeur"], "",
                   "*Compétence non démontrée : aucun niveau de risque n'est annoncé.*", ""]
    else:
        lignes += ["## Pas encore de prévision pour cette saison", ""]
    if pres["mode"] == "niveau":
        lignes.append("Probabilité : **%s** (référence : 33 %%) · source : %s · confiance : %s" % (
            _pct(n["probabilite_annee_extreme"]), n["source"], n["confiance"]))
        lignes.append("")
    lignes += ["## Synthèse", "", b["synthese"], ""]
    c3s = b.get("c3s") or {}
    lignes += ["## Prévision saisonnière officielle (Copernicus C3S)", ""]
    if c3s.get("disponible"):
        comp = c3s.get("competence", {})
        lignes += [
            "| | |", "|---|---|",
            "| Modèle | %s système %s, émission avril |" % (c3s["centre"].upper(), c3s["systeme"]),
            "| Pluie juillet-septembre (moyenne d'ensemble) | %.2f mm/jour |" % c3s["pluie_jas_mm_jour"],
            "| Anomalie standardisée | %+.2f |" % c3s["anomalie_standardisee"],
            "| Membres dans le tiers humide | %s |" % _pct(c3s["part_membres_au_dessus_normale"]),
            "| Probabilité d'année extrême (calibrée CHIRPS) | %s |" % _pct(c3s["probabilite_annee_extreme"]),
            "| Compétence de la calibration (LOYO, %s ans) | AUC %.2f, p = %.3f, BSS %+.2f |" % (
                comp.get("n"), comp.get("auc", float("nan")), comp.get("p_permutation", float("nan")),
                comp.get("brier_skill_score", float("nan"))),
            "",
        ]
    else:
        lignes += ["Non disponible : %s" % c3s.get("raison", "?"), ""]
    p = b.get("projection")
    lignes += ["## État océanique novembre-avril (configurations du mémoire)", ""]
    if p:
        lignes += ["| Configuration | État océanique | Corrélation | Années principales | Part d'événements en année extrême |",
                   "|---|---|---|---|---|"]
        for c in (p.get("configurations") or [])[:3]:
            lignes.append("| C%d | %s | %.2f | %s | %s |" % (
                c["configuration"], c.get("etat_oceanique") or "—", c["correlation"],
                ", ".join(str(a) for a in c.get("annees_principales", [])[:5]) or "—",
                _pct(c.get("part_evenements_en_annee_extreme", 0))))
        lignes += ["", "**Années analogues** : " + ", ".join(
            "%d (%s)" % (a["annee"], "extrême" if a["extreme"] else "normale")
            for a in p.get("analogues") or []), ""]
        fam = p.get("familles_extremes") or {}
        if fam.get("familles"):
            lignes += ["**Familles d'océans des saisons extrêmes** (ressemblance au composite "
                       "de chaque famille, membres antérieurs à la saison seulement) :", "",
                       "| Famille | Saisons | Signature (novembre-avril) | Corrélation |",
                       "|---|---|---|---|"]
            for f in fam["familles"]:
                lignes.append("| %s%s — %s | %s | %s | %s |" % (
                    f["code"], " (la plus proche)" if f["code"] == fam.get("plus_proche") else "",
                    f["nom"], ", ".join(str(a) for a in f["membres_utilises"]) or "pas encore observée",
                    f["signature"],
                    "%.2f" % f["correlation"] if f.get("correlation") is not None else "—"))
            lignes += ["", "*%s*" % fam.get("avertissement", mod_familles.AVERTISSEMENT), ""]
        cp = b.get("competence_projection") or {}
        if cp:
            lo, pr = cp.get("loyo", {}), cp.get("prevision_reelle", {})
            lignes += ["*Indication expérimentale : %s. Compétence mesurée : AUC %.2f (p = %.3f) "
                       "quand seule l'année testée est exclue ; AUC %.2f (p = %.3f) en conditions "
                       "réelles de prévision. %s.*" % (
                           _pct(p["probabilite_experimentale"]) if p.get("probabilite_experimentale") is not None else "n/d",
                           lo.get("auc", float("nan")), lo.get("p_permutation", float("nan")),
                           pr.get("auc", float("nan")), pr.get("p_permutation", float("nan")),
                           (cp.get("verdict") or "")[:1].upper() + (cp.get("verdict") or "")[1:]), ""]
    else:
        lignes += ["Non disponible.", ""]
    if b.get("verification"):
        v = b["verification"]
        lignes += ["## Vérification (saison observée)", "",
                   "Empreinte observée %.0f (seuil %.0f), rang %d : **%s**." % (
                       v["empreinte_observee"], v["seuil"], v["rang"],
                       "année extrême" if v["extreme_observe"] else "année non extrême"), ""]
    if b.get("avertissements"):
        lignes += ["## Avertissements", ""] + ["- " + a for a in b["avertissements"]] + [""]
    d = b["definition"]
    lignes += ["---", "",
               "*Définition : %s ; année extrême = %s (seuil %.0f). Elle retrouve %d des %d "
               "inondations majeures documentées (1999, 2003, 2005, 2009, 2010, 2012, 2020, 2022). "
               "Une probabilité n'est pas une certitude : un niveau « faible » n'exclut pas des "
               "événements locaux intenses.*" % (
                   d["mesure"], d["annee_extreme"], d["seuil"], d["classees_extremes"],
                   d["inondations_documentees"])]
    return _fr("\n".join(lignes)) + "\n"


def mois_lisibles(mois):
    return ["%s %d" % (NOMS_MOIS.get(m, str(m)), a) for a, m in mois]


def arrondir(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)
