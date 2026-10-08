"""Familles d'oceans des saisons extremes: a quelle saison extreme passee
l'ocean de novembre a avril ressemble-t-il ?

Constat (analyse du 08/10/2026, etat nov-avr detrende, 1984-2023): les
saisons les plus extremes ne partagent PAS un meme ocean. Leurs etats se
ressemblent moins entre eux (correlation de motif moyenne 0,18) que les
autres annees entre elles (0,24), et forment deux familles:

  A  1999, 2000, 2012: La Nina, Atlantique tropical frais
     (Nino34 -1,2 ; TSA -1,0 ; TNA -0,6 ecart-type)
  B  2005, 2010, 2020: oceans chauds partout
     (Nino34 +0,9 ; IOBM +1,3 ; TNA +1,4 ; TSA +1,5 ; AMO +1,0)

Les annees 2021-2023 (La Nina + Atlantique tres chaud) sont hybrides et ne
forment pas une famille a part: trois annees consecutives, peut-etre un seul
episode. Le bulletin peut donc repondre "aucune famille".

DESCRIPTIF SEULEMENT. Teste sans fuite (meme protocole que la projection):
la ressemblance au composite des annees extremes a un signal quand seule
l'annee testee est exclue (AUC 0,72-0,75) mais aucun en prevision reelle
(AUC 0,52-0,56, p > 0,29). Elle ne produit donc aucune probabilite et ne
compte pas parmi les variantes de projection (projection.VARIANTES_TESTEES).

Regle anti-fuite: pour le bulletin de l'annee N, le composite d'une famille
ne contient que ses membres ANTERIEURS a N, et la tendance par pixel est
ajustee sur les seules annees anterieures a N. Une famille sans membre
anterieur est "pas encore observee".
"""
import numpy as np

SEUIL_RESSEMBLANCE = 0.30
MIN_ANNEES_TENDANCE = 10

FAMILLES = (
    {"code": "A", "nom": "La Niña et Atlantique tropical frais",
     "annees": (1999, 2000, 2012),
     "signature": "Niño34 −1,2 ; Atlantique tropical sud −1,0 ; nord −0,6 (écarts-types)"},
    {"code": "B", "nom": "Océans chauds partout",
     "annees": (2005, 2010, 2020),
     "signature": "Niño34 +0,9 ; océan Indien +1,3 ; Atlantique tropical nord +1,4, "
                  "sud +1,5 ; AMO +1,0 (écarts-types)"},
)

COMPETENCE_TESTEE = {
    "date": "2026-10-08",
    "loyo_auc": [0.72, 0.75],
    "prevision_reelle_auc": [0.52, 0.56],
    "prevision_reelle_p_min": 0.30,
}

AVERTISSEMENT = ("Ressemblance descriptive : elle n'a pas de valeur de prévision démontrée "
                 "(AUC 0,52-0,56 en prévision réelle, 0,5 = hasard).")


def _correlation(champs, vecteur, w):
    """Correlation de motif ponderee (meme formule que projection._correlation;
    copiee pour que le kit de scenario se relise en numpy pur sur le serveur)."""
    a = (vecteur - vecteur.mean()) * w
    c = (champs - champs.mean(1, keepdims=True)) * w
    return (c @ a) / (np.linalg.norm(c, axis=1) * np.linalg.norm(a))


def preparer(etat_de, annees_connues, annee):
    """Composites detrendes de chaque famille, avec les seules annees < annee.

    Renvoie {"ybar", "pente", "composites": {code: vecteur ou None},
    "membres": {code: [annees]}} ou None si trop peu d'annees anterieures.
    C'est ce qui est range dans le kit de scenario (veille.artefacts).
    """
    passees = sorted(a for a in annees_connues if a < annee)
    if len(passees) < MIN_ANNEES_TENDANCE:
        return None
    etats = {a: np.asarray(etat_de(a), float) for a in passees}
    y = np.asarray(passees, float)
    X = np.array([etats[a] for a in passees])
    ybar = float(y.mean())
    yc = y - ybar
    pente = (yc @ (X - X.mean(0))) / (yc @ yc)
    prep = {"ybar": ybar, "pente": pente, "composites": {}, "membres": {}}
    for f in FAMILLES:
        membres = [a for a in f["annees"] if a in etats]
        prep["membres"][f["code"]] = membres
        prep["composites"][f["code"]] = (
            np.mean([etats[a] - pente * (a - ybar) for a in membres], axis=0) if membres else None)
    return prep


def evaluer(prep, champ, annee, w):
    """Ressemblance d'un etat aux familles preparees (numpy pur)."""
    resultat = {"seuil": SEUIL_RESSEMBLANCE, "plus_proche": None,
                "avertissement": AVERTISSEMENT, "familles": []}
    if prep is None:
        resultat["familles"] = [dict(_base(f), membres_utilises=[], correlation=None)
                                for f in FAMILLES]
        return resultat
    cible = np.asarray(champ, float) - np.asarray(prep["pente"], float) * (annee - prep["ybar"])
    w = np.asarray(w, float)
    for f in FAMILLES:
        comp = prep["composites"].get(f["code"])
        r = None
        if comp is not None:
            r = round(float(_correlation(np.asarray(comp, float)[None], cible, w)[0]), 3)
        resultat["familles"].append(dict(_base(f), membres_utilises=list(prep["membres"].get(
            f["code"], [])), correlation=r))
    notees = [f for f in resultat["familles"]
              if f["correlation"] is not None and f["correlation"] >= SEUIL_RESSEMBLANCE]
    if notees:
        resultat["plus_proche"] = max(notees, key=lambda f: f["correlation"])["code"]
    return resultat


def ressemblance(etat_de, annees_connues, champ, annee, w):
    """Ressemblance de `champ` (etat nov-avr de `annee`) a chaque famille.

    etat_de: fonction annee -> etat nov-avr (vecteur masque);
    annees_connues: annees dont l'etat est complet et la saison observee;
    w: poids cos(lat) du masque. Seules les annees < annee sont utilisees.
    """
    return evaluer(preparer(etat_de, annees_connues, annee), champ, annee, w)


def _base(f):
    return {"code": f["code"], "nom": f["nom"], "annees": list(f["annees"]),
            "signature": f["signature"]}


def depuis_contexte(ctx, champ, annee):
    """Version branchee sur projection.Contexte (cube SST du bulletin)."""
    return ressemblance(ctx.etat, ctx.annees_observees(), champ, annee, ctx.w)


def preparer_contexte(ctx, annee):
    return preparer(ctx.etat, ctx.annees_observees(), annee)


# =============================================================================
# Rangement dans le kit de scenario (tableaux numpy simples)
# =============================================================================
def vers_kit(prep):
    """prep -> tableaux pour np.savez (familles sans membre exclues)."""
    if prep is None:
        return {}
    codes = [c for c, v in prep["composites"].items() if v is not None]
    if not codes:
        return {}
    return {"fam_codes": np.array(codes),
            "fam_membres": np.array([",".join(str(a) for a in prep["membres"][c]) for c in codes]),
            "fam_composites": np.array([prep["composites"][c] for c in codes], dtype="float16"),
            "fam_pente": np.asarray(prep["pente"], dtype="float32"),
            "fam_ybar": np.float64(prep["ybar"])}


def depuis_kit(kit):
    """Tableaux du kit -> prep (None si kit ancien, sans familles)."""
    if "fam_codes" not in kit:
        return None
    codes = [str(c) for c in kit["fam_codes"]]
    membres = [str(m) for m in kit["fam_membres"]]
    prep = {"ybar": float(kit["fam_ybar"]), "pente": kit["fam_pente"].astype("float64"),
            "composites": {f["code"]: None for f in FAMILLES},
            "membres": {f["code"]: [] for f in FAMILLES}}
    for i, c in enumerate(codes):
        prep["composites"][c] = kit["fam_composites"][i].astype("float64")
        prep["membres"][c] = [int(a) for a in membres[i].split(",") if a]
    return prep


def phrase(fam):
    """Phrase de synthese (None si rien a dire)."""
    if not fam or not fam.get("familles"):
        return None
    calc = [f for f in fam["familles"] if f.get("correlation") is not None]
    if not calc:
        return None
    detail = " ; ".join("%s (%s) r = %.2f" % (f["code"], "/".join(str(a) for a in f["membres_utilises"]),
                                              f["correlation"]) for f in calc)
    code = fam.get("plus_proche")
    if code:
        f = next(f for f in fam["familles"] if f["code"] == code)
        tete = ("Familles d'océans des saisons extrêmes : l'océan ressemble surtout à la "
                "famille %s, celle des saisons %s (%s)" % (
                    code, "/".join(str(a) for a in f["membres_utilises"]), f["nom"]))
    else:
        tete = ("Familles d'océans des saisons extrêmes : l'océan ne ressemble nettement à "
                "aucune des deux (seuil r = %.2f)" % fam["seuil"])
    return "%s [%s]. %s" % (tete, detail, fam.get("avertissement", AVERTISSEMENT))
