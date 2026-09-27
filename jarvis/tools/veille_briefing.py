"""Outil present_bulletin_briefing: lance le briefing vocal d'un bulletin.

"Jarvis, presente-moi le bulletin 2027": l'outil ne fait que DEMANDER au
widget de lancer la presentation guidee (jarvis/briefing.py). Les etapes,
cartes et narrations sont ensuite composees par le code, sans modele. Le
programme est une liste fermee, relayee par le serveur (app.PROGRAMMES):
le modele ne peut rien lancer d'autre.
"""
from .common import ToolInputError, champ_entier

NAME = "present_bulletin_briefing"
LABEL = "Lancement du briefing de veille"
PERMISSION = "public"
DATASETS = ()

DESCRIPTION = (
    "LANCE LE BRIEFING VOCAL du bulletin de veille pre-saison: presentation "
    "guidee en plein ecran, 8 etapes (verdict, carte de l'ocean novembre-avril, "
    "configuration du memoire, evolution pendant la veille, annees analogues, "
    "prevision Copernicus, fiabilite, ce qu'il faut retenir), lue a voix haute "
    "et composee a partir des donnees. A utiliser quand on te demande de "
    "presenter, expliquer en detail ou faire un briefing du bulletin. year: "
    "saison (defaut: le bulletin le plus recent). Apres l'appel, annonce "
    "seulement en une phrase que le briefing commence: ne donne pas les "
    "chiffres, la presentation les dira."
)

SCHEMA = {
    "type": "object",
    "properties": {"year": {"type": "integer", "description": "Saison du bulletin."}},
}


def run(params, data):
    from veille import production
    dispo = production.bulletins_disponibles()
    if not dispo:
        raise ToolInputError("Aucun bulletin de veille n'a ete produit.")
    annee = champ_entier(params, "year", mini=1981, maxi=2100)
    if annee is not None and annee not in dispo:
        raise ToolInputError("Pas de bulletin pour %d. Disponibles: %s."
                             % (annee, ", ".join(str(a) for a in sorted(dispo))))
    annee = dispo[0] if annee is None else annee
    return {
        "presentation": {"programme": "briefing", "annee": annee},
        "lancee": True,
        "consigne": ("Le briefing demarre a la fin de ta reponse, en plein ecran et a "
                     "voix haute. Annonce-le en une phrase courte, sans chiffres."),
    }
