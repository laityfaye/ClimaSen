"""Outil generate_report: un rapport professionnel a partir des donnees.

Un seul outil pour les deux temps de la demande:
  - si un champ manque ou est ambigu (zone, periode, saison), il renvoie UNE
    question de clarification, avec ses options; la session est notee et
    l'appel suivant ne pourra plus en renvoyer (valeurs par defaut, ecrites
    dans le rapport comme hypotheses);
  - sinon il lance la production en arriere-plan (jarvis/rapports) et rend
    l'identifiant du rapport: le widget affiche la progression puis les
    boutons PDF, Word et HTML.

Le modele ne recoit aucun chiffre du rapport ici: il n'a donc rien a en
dire, sinon l'annoncer.
"""
from ..rapports import HORIZONS, LIBELLES_TYPE, PUBLICS, figures_reference, moteur_figures
from .common import METRIQUES, PHASES_TOUTES, ToolInputError

NAME = "generate_report"
LABEL = "Préparation d'un rapport"
PERMISSION = "public"
DATASETS = ()

DESCRIPTION = (
    "Genere un RAPPORT PROFESSIONNEL telechargeable (PDF, Word, HTML) a partir des donnees de "
    "la plateforme: structure fixe (contexte, resume executif, methodologie et sources, "
    "analyse illustree de cartes, graphiques et tableaux, conclusions et recommandations, "
    "limites), chaque chiffre lu dans les donnees et date. Types: historique (evenements "
    "extremes 1981-2023 d'une zone, d'une periode ou d'une phase), teleconnexions "
    "(correlations indices SST / pluies extremes, configurations oceaniques), vulnerabilite "
    "(indice de risque d'une zone: region, departement, arrondissement ou commune, ou "
    "classement national), veille (bulletin pre-saison d'une saison, avec zones "
    "prioritaires). A utiliser quand on demande un rapport, un document, un bulletin a "
    "telecharger ou a imprimer. Passe ce que la demande precise (zone en toutes lettres, "
    "annees, phase, horizon 'prochaine' pour 'l'hivernage prochain', public). Si l'outil "
    "renvoie statut=question, pose CETTE question telle quelle avec ses options, rien "
    "d'autre, puis rappelle l'outil avec la 'valeur' choisie. Si statut=lance, annonce en "
    "une ou deux phrases que le rapport se prepare (titre, zone, hypotheses retenues) : "
    "n'invente aucun chiffre, le rapport les contient. reference_figures: figures validees "
    "a ajouter (ids: %s). extra_figures: figures supplementaires decrites comme pour "
    "make_custom_figure, si l'utilisateur demande un visuel que le rapport n'a pas."
    % ", ".join(sorted(e["id"] for e in figures_reference._entrees().values()))
)

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(LIBELLES_TYPE),
                 "description": "Type de rapport. Omettre si la demande ne permet pas de le "
                                "deduire (l'outil posera la question)."},
        "zone": {"type": "string",
                 "description": "Lieu en toutes lettres (region, departement, arrondissement, "
                                "commune) ou 'Senegal'."},
        "zone_code": {"type": "string",
                      "description": "Code d'une option proposee par une question precedente."},
        "year_min": {"type": "integer", "description": "Premiere annee (historique)."},
        "year_max": {"type": "integer", "description": "Derniere annee (historique)."},
        "phase": {"type": "string", "enum": PHASES_TOUTES,
                  "description": "Phase de saison (historique, teleconnexions)."},
        "season": {"type": "integer", "description": "Saison visee (veille)."},
        "horizon": {"type": "string", "enum": list(HORIZONS),
                    "description": "Veille: 'prochaine' (hivernage prochain) ou 'en_cours'. "
                                   "La saison est calculee a partir de la date du jour."},
        "metric": {"type": "string", "enum": sorted(METRIQUES),
                   "description": "Teleconnexions: metrique (defaut max_precip)."},
        "audience": {"type": "string", "enum": list(PUBLICS),
                     "description": "decideur (protection civile, collectivites) ou technique "
                                    "(ANSD, ANACIM, chercheurs)."},
        "request": {"type": "string", "description": "La demande, reformulee en une phrase."},
        "reference_figures": {"type": "array", "items": {"type": "string"}},
        "extra_figures": {"type": "array", "items": {"type": "object"}},
    },
}


def run(params, data, rapports=None, session_id="", profile="public"):
    from ..rapports.taches import QuotaRapports  # import differe: cycle tools <-> rapports
    if rapports is None:
        raise ToolInputError("La generation de rapports n'est pas disponible ici.")
    for brute in params.get("extra_figures") or []:
        try:  # refus explicite tout de suite, plutot qu'une figure absente du rapport
            moteur_figures.Plan(brute)
        except moteur_figures.SpecInvalide as exc:
            raise ToolInputError("extra_figures: %s" % exc)
    r = rapports.preparer(params, session_id)
    if r["statut"] == "question":
        return r
    spec = r["spec"]
    try:
        tache = rapports.lancer(session_id, spec, profile, params)
    except QuotaRapports as exc:
        raise ToolInputError(str(exc))
    return {
        "statut": "lance" if not tache.depuis_cache else "pret",
        "rapport_id": tache.id,
        "titre": tache.titre,
        "sous_titre": tache.sous_titre,
        "demande_comprise": spec.vue(),
        "consigne": ("Le rapport se prepare et s'affiche dans la conversation avec sa "
                     "progression, puis des boutons PDF, Word et HTML. Annonce-le en une ou deux "
                     "phrases (type, zone, hypotheses retenues), sans aucun chiffre."),
    }
