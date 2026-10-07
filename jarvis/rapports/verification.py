"""Verification de la redaction du modele, avant toute mise en page.

Quatre controles, dans cet ordre; chacun renvoie des motifs lisibles, qui
repartent au modele pour une nouvelle tentative:

  1. structure: sections attendues, resume court, recommandations presentes;
  2. renvois: tout {{fait:x}} doit exister dans le registre;
  3. nombres: un nombre ecrit en clair doit etre la valeur affichee d'un fait,
     ou figurer dans le gabarit ecrit par le code (annees, seuils de
     methode). Sinon il est INVENTE, et la redaction est refusee;
  4. lexique: aucun langage de certitude ("provoquera", "garantit"...), et
     aucune phrase qui ferait passer le rapport pour un substitut a l'ANACIM.

Le statut d'un paragraphe (observe, correle, projete) n'est pas cru sur
parole: il est recalcule a partir des faits qu'il cite (voir statut_de).
"""
import re

from .faits import RENVOI

SECTIONS_IA = ("contexte", "resume", "analyse", "conclusions")
MAX_MOTS_RESUME = 220

# Noms propres et sigles qui contiennent des chiffres: ce ne sont pas des valeurs.
NOMS_A_CHIFFRES = [
    r"Ni[nñ]o\s?(?:1\s?\+\s?2|3[.,]4|12|34|3|4)\b", r"\bATL3\b", r"\bRGPH[\s-]?5\b",
    r"\bRGPH\s?2013\b", r"\bC3S\b", r"\bSEAS5\b", r"\bOISST\s?v2\b", r"\bCHIRPS\s?v2\b",
    r"\bEHCVM\s?2021-2022\b", r"\bCOD-AB\b", r"\bAR\s?1\b", r"\bIC\s?(?:à\s)?95\s?%",
    r"\b95\s?%", r"\bPhase[_\s]?[123]\b", r"\bC\d{1,2}\b", r"\bv0?2\b", r"\bG\d\b",
]
_NOMS = re.compile("|".join(NOMS_A_CHIFFRES), re.IGNORECASE)
NOMBRE = re.compile(r"(?<![\w])[-−+]?\d+(?:[   ]\d{3})*(?:[,.]\d+)?")

CERTITUDE = [
    r"\bprovoquer(?:a|ont)\b", r"\bentra[iî]ner(?:a|ont)\b", r"\bcausera(?:it)?\b",
    r"\bgaranti(?:t|r|e|ssent)\b", r"\bcertainement\b", r"\bsans aucun doute\b",
    r"\bil est certain\b", r"\bassurément\b", r"\bà coup sûr\b", r"\bva (?:pleuvoir|provoquer|"
    r"entra[iî]ner|causer|inonder)\b", r"\bprédit avec certitude\b", r"\bcause directe\b",
    r"\binévitablement\b", r"\bforcément\b", r"\bprouve que\b", r"\bdémontre que\b",
]
_CERTITUDE = re.compile("|".join(CERTITUDE), re.IGNORECASE)
_REMPLACE = re.compile(r"remplac\w*", re.IGNORECASE)
_NE_REMPLACE_PAS = re.compile(r"\bne\s+(?:les?\s+|l'|la\s+)?remplac\w*\s+pas\b|\bsans\s+(?:les?\s+|l'|la\s+)?remplacer\b",
                              re.IGNORECASE)

ORDRE_STATUTS = ("projete", "correle", "observe", "methode")


def canonique(token: str) -> str:
    t = token.replace(" ", "").replace(" ", "").replace(" ", "")
    t = t.replace("−", "-").replace(",", ".").lstrip("+")
    if "." in t:
        t = t.rstrip("0").rstrip(".") or "0"
    if t.startswith("-") and t[1:] in ("0",):
        t = "0"
    return t


def nombres(texte: str) -> list:
    """Nombres ecrits en clair, renvois et noms propres retires."""
    nettoye = RENVOI.sub(" ", texte or "")
    nettoye = _NOMS.sub(" ", nettoye)
    return [canonique(m.group(0)) for m in NOMBRE.finditer(nettoye)]


def autorises(registre, textes_code=()) -> set:
    """Nombres admis en clair: valeurs affichees des faits, periodes, et tout
    nombre ecrit par le code (gabarit, recommandations, hypotheses)."""
    permis = set()
    for f in registre:
        for texte in (f.texte(), f.periode):
            permis.update(nombres(texte))
    for texte in textes_code:
        permis.update(nombres(registre.remplacer(texte) if RENVOI.search(texte or "") else texte))
        permis.update(nombres(texte))
    return permis


def statut_de(texte: str, registre, statut_propose=None):
    """Statut le plus 'fort' parmi les faits cites (projete > correle > observe).

    Un paragraphe qui cite une projection est une projection, quoi qu'en dise
    le modele."""
    cites = registre.statuts_cites(texte)
    for s in ORDRE_STATUTS[:3]:
        if s in cites:
            return s
    if statut_propose in ORDRE_STATUTS and not cites:
        return statut_propose if statut_propose != "projete" else None
    return "methode" if "methode" in cites else None


def verifier(redaction: dict, registre, permis: set) -> list:
    """Liste des motifs de refus (vide = redaction acceptee)."""
    motifs = []
    if not isinstance(redaction, dict):
        return ["La reponse n'est pas un objet JSON."]
    for cle in SECTIONS_IA:
        bloc = redaction.get(cle)
        if not isinstance(bloc, list) or not bloc:
            motifs.append("Section %r absente ou vide." % cle)
            continue
        for i, p in enumerate(bloc):
            if not isinstance(p, dict) or not str(p.get("texte", "")).strip():
                motifs.append("Section %r, paragraphe %d : texte manquant." % (cle, i + 1))
    recos = redaction.get("recommandations")
    if not isinstance(recos, list) or not [r for r in recos if str(r).strip()]:
        motifs.append("Au moins une recommandation operationnelle est requise.")
    if motifs:
        return motifs

    paragraphes = [(cle, p["texte"]) for cle in SECTIONS_IA for p in redaction[cle]]
    paragraphes += [("recommandations", str(r)) for r in recos]
    mots_resume = sum(len(registre.remplacer(p["texte"]).split())
                      for p in redaction["resume"] if not registre.inconnus(p["texte"]))
    if mots_resume > MAX_MOTS_RESUME:
        motifs.append("Resume executif trop long (%d mots, %d au plus)."
                      % (mots_resume, MAX_MOTS_RESUME))
    for cle, texte in paragraphes:
        inconnus = registre.inconnus(texte)
        if inconnus:
            motifs.append("Section %r : renvoi(s) vers des faits inexistants : %s. N'utilise que "
                          "les identifiants fournis." % (cle, ", ".join(sorted(set(inconnus)))))
        hors = sorted({n for n in nombres(texte) if n not in permis})
        if hors:
            motifs.append("Section %r : nombre(s) ecrit(s) en clair qui ne viennent d'aucun fait : "
                          "%s. Remplace-les par un renvoi {{fait:id}} ou supprime-les."
                          % (cle, ", ".join(hors)))
        m = _CERTITUDE.search(texte)
        if m:
            motifs.append("Section %r : formulation de certitude interdite (%r) : un rapport "
                          "decrit des observations, des correlations et des projections, jamais "
                          "des certitudes." % (cle, m.group(0)))
        if _REMPLACE.search(texte) and not _NE_REMPLACE_PAS.search(texte):
            motifs.append("Section %r : ne laisse pas entendre que ce rapport remplace les "
                          "alertes officielles (ANACIM)." % cle)
    return motifs
