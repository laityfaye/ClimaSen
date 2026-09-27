"""Outil admin draft_bulletin_release: bulletin pret a diffuser.

Compose les trois versions diffusables d'un bulletin (message court, resume
d'une page, document Word) et les MONTRE, mais n'ecrit rien: il depose une
proposition "veille_diffusion" que l'utilisateur approuve dans la console
(protocole de jarvis/actions.py). Le texte vient du code (veille.diffusion),
pas du modele: aucun chiffre ne peut etre deforme en route.

Rien n'est envoye a personne: l'envoi reste un geste humain.
"""
from .common import ToolInputError, champ_entier

NAME = "draft_bulletin_release"
LABEL = "Préparation du bulletin à diffuser"
PERMISSION = "admin"
DATASETS = ()

DESCRIPTION = (
    "Prepare la DIFFUSION d'un bulletin de veille pre-saison aux acteurs "
    "operationnels (protection civile, mairies, ONG): message court SMS/"
    "WhatsApp (<= 320 caracteres), resume d'une page, document Word formel. "
    "Renvoie le SMS et le resume pour relecture et DEPOSE une proposition "
    "d'ecriture des trois fichiers dans outputs/veille/diffusion/, a approuver "
    "dans la console. N'ecrit rien et n'envoie rien. year: saison (defaut: la "
    "plus recente)."
)

SCHEMA = {
    "type": "object",
    "properties": {"year": {"type": "integer", "description": "Saison du bulletin."}},
}


def run(params, data, session_id=None, registre=None):
    from veille import diffusion, production

    dispo = production.bulletins_disponibles()
    if not dispo:
        raise ToolInputError("Aucun bulletin de veille n'a ete produit.")
    annee = champ_entier(params, "year", mini=1981, maxi=2100)
    annee = dispo[0] if annee is None else annee
    b = production.lire_bulletin(annee)
    if b is None:
        raise ToolInputError("Pas de bulletin pour %d. Disponibles: %s."
                             % (annee, ", ".join(str(a) for a in sorted(dispo))))
    if registre is None or session_id is None:  # pragma: no cover - garde-fou
        raise ToolInputError("Contexte de session absent.")

    apercu = diffusion.apercu(b)
    action = registre.deposer(
        session_id, "veille_diffusion",
        "Bulletin de veille %d : écrire SMS, résumé et document Word" % annee,
        {"annee": annee, "niveau": b["niveau_risque"]["libelle"],
         "sms": apercu["sms"], "dossier": "outputs/veille/diffusion/",
         "fichiers": ["veille_%d.sms.txt" % annee, "veille_%d.resume.md" % annee,
                      "veille_%d.docx" % annee]},
        {"annee": annee},
    )
    return {
        "statut": "proposition_deposee",
        "action_id": action.id,
        "annee": annee,
        "sms": apercu["sms"],
        "sms_caracteres": apercu["sms_caracteres"],
        "resume_markdown": apercu["resume_markdown"],
        "message": ("Proposition deposee: RIEN n'est ecrit ni envoye. Montre le SMS, "
                    "resume le document, et invite l'utilisateur a approuver dans la "
                    "console. L'envoi aux destinataires reste un geste humain."),
    }
