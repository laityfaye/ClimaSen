"""Chaine complete d'un rapport: collecte -> redaction -> assemblage -> exports.

Utilisee par le gestionnaire de taches (taches.py, asynchrone) et par les
tests; chaque etape bloquante (pandas, matplotlib, Chromium) tourne hors de la
boucle d'evenements.
"""
import asyncio
import logging

from . import assemblage, manifest, redaction
from .collecteurs import CollecteImpossible, historique, teleconnexions, veille, vulnerabilite
from .rendus import ExportIndisponible, en_docx, en_html, en_pdf

log = logging.getLogger("jarvis.rapports")

COLLECTEURS = {"historique": historique.collecter, "teleconnexions": teleconnexions.collecter,
               "vulnerabilite": vulnerabilite.collecter, "veille": veille.collecter}
# Jeux de donnees par type (noms de jarvis/tools/dataset.py). Les optionnels
# enrichissent le rapport; leur absence ne l'empeche pas.
JEUX = {"historique": (("events",), ("vulnerabilite",)),
        "teleconnexions": (("correlations",), ("clustering", "events")),
        "vulnerabilite": (("vulnerabilite",), ()),
        "veille": (("vulnerabilite",), ())}


def charger_donnees(type_) -> dict:
    from ..tools import dataset
    requis, optionnels = JEUX[type_]
    donnees = {nom: dataset.get(nom) for nom in requis}
    for nom in optionnels:
        try:
            donnees[nom] = dataset.get(nom)
        except dataset.DataUnavailableError:
            log.warning("Jeu optionnel %s indisponible pour un rapport %s.", nom, type_)
    return donnees


def collecter(spec, donnees, gazetteer=None):
    collecte = COLLECTEURS[spec.type](spec, donnees, gazetteer)
    retirees = redaction.nettoyer_gabarit(collecte, collecte.registre)
    if retirees:
        log.info("Gabarit: %d phrase(s) sans donnees retirees.", len(retirees))
    return collecte


def figures_en_plus(spec, gazetteer=None):
    """Figures de reference et figures a la demande demandees dans la spec."""
    from . import figures_reference, moteur_figures
    extras, notes = [], []
    for ident in spec.figures_reference:
        try:
            extras.append(("analyse", figures_reference.figure(ident)))
        except KeyError as exc:
            notes.append(str(exc))
    for brute in spec.figures_supplementaires:
        try:
            bloc, _ = moteur_figures.pour_rapport(brute)
            extras.append(("analyse", bloc))
        except moteur_figures.SpecInvalide as exc:
            notes.append("Figure demandée non produite : %s" % exc)
    return extras, notes


def exporter(rapport, avec_pdf=True) -> dict:
    """{"html": bytes, "docx": bytes, "pdf": bytes|None, "erreurs": {...}}."""
    html = en_html(rapport)
    sorties = {"html": html.encode("utf-8"), "docx": en_docx(rapport), "pdf": None,
               "erreurs": {}}
    if avec_pdf:
        try:
            sorties["pdf"] = en_pdf(html, rapport.meta)
        except ExportIndisponible as exc:
            log.warning("PDF non produit: %s", exc)
            sorties["erreurs"]["pdf"] = str(exc)
    return sorties


def preparer_collecte(spec, gazetteer=None):
    """Donnees, faits et visuels d'une spec (bloquant). (collecte, extras)."""
    donnees = charger_donnees(spec.type)
    collecte = collecter(spec, donnees, gazetteer)
    extras, notes = figures_en_plus(spec, gazetteer)
    collecte.limites_specifiques.extend(notes)
    return collecte, extras


def finaliser(rapport_id, spec, collecte, texte, journal, extras=(), exclus=frozenset(),
              version=1, avec_pdf=True):
    """Assemblage et exports (bloquant). (rapport, sorties)."""
    rapport = assemblage.assembler(rapport_id, spec, collecte, texte, journal, manifest.lire(),
                                   extras, exclus, version)
    sorties = exporter(rapport, avec_pdf)
    sorties["faits_csv"] = collecte.registre.en_csv().encode("utf-8-sig")
    return rapport, sorties


async def signaler(etape, texte):
    if etape is not None:
        r = etape(texte)
        if asyncio.iscoroutine(r):
            await r


async def produire(rapport_id, spec, client=None, profile="public", gazetteer=None,
                   etape=None, avec_pdf=True, details=None):
    """Rapport complet. etape(libelle) est appele a chaque etape (progression).
    details (dict), s'il est fourni, recoit les extras: le gestionnaire les
    garde pour les versions suivantes."""
    await signaler(etape, "Lecture des données de la plateforme")
    await signaler(etape, "Calcul des faits, cartes et graphiques")
    collecte, extras = await asyncio.to_thread(preparer_collecte, spec, gazetteer)
    await signaler(etape, "Rédaction")
    texte, journal = await redaction.rediger(collecte, spec, client, profile)
    await signaler(etape, "Mise en page")
    await signaler(etape, "Export HTML, Word et PDF")
    rapport, sorties = await asyncio.to_thread(finaliser, rapport_id, spec, collecte, texte,
                                               journal, extras, frozenset(), 1, avec_pdf)
    if details is not None:
        details.update({"extras": extras, "texte": texte})
    return rapport, collecte, journal, sorties


__all__ = ["produire", "collecter", "exporter", "charger_donnees", "CollecteImpossible"]
