"""Redaction par Claude, sous controle, avec repli sur le gabarit.

Le modele recoit les faits (identifiant, sens, statut, valeur affichee) et la
redaction gabarit ecrite par le code; il renvoie une version amelioree en
JSON (sorties structurees), ou chaque valeur est un renvoi {{fait:id}}.

La reponse passe par verification.verifier. En cas de refus, le modele
recoit les motifs et reessaie (2 nouvelles tentatives au plus). Au-dela, ou
si l'API est indisponible, le rapport sort avec la redaction gabarit: il est
moins fluide mais exact, et le journal le dit.
"""
import json
import logging

from ..claude_client import load_system_prompt
from . import textes_fixes as tf
from . import verification

log = logging.getLogger("jarvis.rapports.redaction")

TENTATIVES = 3
STATUTS_SCHEMA = ["observe", "correle", "projete", "methode", "aucun"]

_PARAGRAPHES = {"type": "array", "items": {
    "type": "object",
    "properties": {"texte": {"type": "string"},
                   "statut": {"type": "string", "enum": STATUTS_SCHEMA}},
    "required": ["texte", "statut"], "additionalProperties": False}}

SCHEMA = {
    "type": "object",
    "properties": {
        "contexte": _PARAGRAPHES,
        "resume": _PARAGRAPHES,
        "analyse": _PARAGRAPHES,
        "conclusions": _PARAGRAPHES,
        "recommandations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["contexte", "resume", "analyse", "conclusions", "recommandations"],
    "additionalProperties": False,
}


# Modification d'un rapport existant: meme schema, plus une note destinee a
# l'utilisateur (ce qui a ete change, ou pourquoi la demande ne peut pas
# l'etre). La note n'entre jamais dans le rapport.
SCHEMA_MODIFICATION = {
    "type": "object",
    "properties": dict(SCHEMA["properties"], note={"type": "string"}),
    "required": SCHEMA["required"] + ["note"],
    "additionalProperties": False,
}
MAX_INSTRUCTION = 1500


def gabarit(collecte) -> dict:
    """La redaction du code, au format de la reponse du modele."""
    sortie = {}
    for cle in verification.SECTIONS_IA:
        sortie[cle] = [{"texte": t, "statut": s or "aucun"}
                       for t, s in collecte.gabarit.get(cle, [])]
    sortie["recommandations"] = list(collecte.recommandations)
    return sortie


def textes_du_code(collecte, spec) -> list:
    textes = [t for blocs in collecte.gabarit.values() for t, _ in blocs]
    textes += list(collecte.recommandations) + list(spec.hypotheses)
    textes += [collecte.titre, collecte.sous_titre, collecte.periode]
    return textes


def nettoyer_gabarit(collecte, registre) -> list:
    """Retire du gabarit les phrases qui citent un fait absent (donnee manquante
    pour cette zone). Renvoie les phrases retirees, pour le journal."""
    retirees = []
    for cle, blocs in list(collecte.gabarit.items()):
        gardes = []
        for t, s in blocs:
            if registre.inconnus(t):
                retirees.append(t)
            else:
                gardes.append((t, s))
        collecte.gabarit[cle] = gardes
    recos = []
    for r in collecte.recommandations:
        if registre.inconnus(r):
            retirees.append(r)
        else:
            recos.append(r)
    collecte.recommandations = recos
    return retirees


def _message(collecte, spec) -> str:
    return json.dumps({
        "demande": {"type": spec.type, "zone": collecte.zone, "periode": collecte.periode,
                    "public": tf.PUBLICS[spec.public], "titre": collecte.titre,
                    "sous_titre": collecte.sous_titre, "formulation": spec.demande,
                    "hypotheses": spec.hypotheses},
        "faits": collecte.registre.pour_redaction(),
        "gabarit": {k: v for k, v in gabarit(collecte).items() if k != "recommandations"},
        "recommandations_gabarit": collecte.recommandations,
        "consignes": collecte.consignes,
        "limites": [tf.LIMITES[k] for k in collecte.limites] + collecte.limites_specifiques,
    }, ensure_ascii=False, indent=1)


async def rediger(collecte, spec, client, profile="public") -> tuple:
    """(redaction, journal). journal = {"mode": "ia"|"gabarit", "modele",
    "tentatives", "motifs", "usage"}."""
    registre = collecte.registre
    permis = verification.autorises(registre, textes_du_code(collecte, spec))
    journal = {"mode": "gabarit", "modele": "aucun", "tentatives": 0, "motifs": [],
               "usage": {}}
    base = gabarit(collecte)
    if client is None or not hasattr(client, "generer_json"):
        journal["motifs"].append("redaction IA indisponible")
        return base, journal
    system = load_system_prompt("rapport")
    messages = [{"role": "user", "content": _message(collecte, spec)}]
    for essai in range(1, TENTATIVES + 1):
        journal["tentatives"] = essai
        try:
            reponse = await client.generer_json(system, messages, SCHEMA, profile=profile)
        except Exception as exc:  # API indisponible, quota, delai: on garde le gabarit
            log.warning("Redaction IA impossible: %s", exc)
            journal["motifs"].append("API indisponible (%s)" % type(exc).__name__)
            return base, journal
        for cle, val in (reponse.get("usage") or {}).items():
            journal["usage"][cle] = journal["usage"].get(cle, 0) + (val or 0)
        journal["modele"] = reponse.get("model", "inconnu")
        texte = reponse.get("text") or ""
        try:
            proposee = json.loads(texte)
        except ValueError:
            proposee = None
            motifs = ["La reponse n'est pas du JSON valide."]
        else:
            motifs = verification.verifier(proposee, registre, permis)
        if not motifs:
            journal["mode"] = "ia"
            return proposee, journal
        journal["motifs"].extend("tentative %d : %s" % (essai, m) for m in motifs)
        log.info("Redaction refusee (tentative %d): %s", essai, " | ".join(motifs)[:500])
        messages = messages + [
            {"role": "assistant", "content": texte or "{}"},
            {"role": "user", "content": "Ta redaction est refusee pour ces raisons :\n- "
             + "\n- ".join(motifs) + "\nCorrige-la et renvoie la redaction complete."}]
    journal["modele"] += " (repli gabarit)"
    return base, journal


async def modifier(collecte, spec, client, actuelle, instruction, profile="public") -> tuple:
    """Applique une demande de modification a la redaction ACTUELLE.

    (redaction | None, journal, note). None: la modification n'a pas ete
    appliquee (redaction IA indisponible ou refusee a la verification); le
    rapport garde alors sa redaction actuelle, et la note dit pourquoi.
    """
    registre = collecte.registre
    journal = {"mode": "inchange", "modele": "aucun", "tentatives": 0, "motifs": [],
               "usage": {}}
    if client is None or not hasattr(client, "generer_json"):
        return None, journal, ("Les modifications de texte demandent la rédaction assistée, "
                               "indisponible sur ce serveur.")
    permis = verification.autorises(registre, textes_du_code(collecte, spec)
                                    + [_texte_redaction(actuelle)])
    charge = json.loads(_message(collecte, spec))
    charge["redaction_actuelle"] = actuelle
    charge["demande_de_modification"] = instruction[:MAX_INSTRUCTION]
    system = load_system_prompt("rapport")
    messages = [{"role": "user", "content": json.dumps(charge, ensure_ascii=False, indent=1)}]
    note = ""
    for essai in range(1, TENTATIVES + 1):
        journal["tentatives"] = essai
        try:
            reponse = await client.generer_json(system, messages, SCHEMA_MODIFICATION,
                                                profile=profile)
        except Exception as exc:
            log.warning("Modification IA impossible: %s", exc)
            journal["motifs"].append("API indisponible (%s)" % type(exc).__name__)
            return None, journal, "La rédaction assistée est momentanément indisponible."
        for cle, val in (reponse.get("usage") or {}).items():
            journal["usage"][cle] = journal["usage"].get(cle, 0) + (val or 0)
        journal["modele"] = reponse.get("model", "inconnu")
        texte = reponse.get("text") or ""
        try:
            proposee = json.loads(texte)
        except ValueError:
            proposee, motifs = None, ["La reponse n'est pas du JSON valide."]
        else:
            note = str((proposee or {}).pop("note", "") if isinstance(proposee, dict) else "")
            motifs = verification.verifier(proposee, registre, permis)
        if not motifs:
            journal["mode"] = "ia"
            return proposee, journal, note
        journal["motifs"].extend("tentative %d : %s" % (essai, m) for m in motifs)
        messages = messages + [
            {"role": "assistant", "content": texte or "{}"},
            {"role": "user", "content": "Ta modification est refusee pour ces raisons :\n- "
             + "\n- ".join(motifs) + "\nCorrige-la et renvoie la redaction complete."}]
    return None, journal, ("La modification n'a pas pu être appliquée sans enfreindre les règles "
                           "du rapport : " + "; ".join(journal["motifs"][-2:]))


def _texte_redaction(red) -> str:
    morceaux = []
    for cle in verification.SECTIONS_IA:
        morceaux.extend(p.get("texte", "") for p in red.get(cle, []) if isinstance(p, dict))
    morceaux.extend(str(r) for r in red.get("recommandations", []))
    return " ".join(morceaux)
