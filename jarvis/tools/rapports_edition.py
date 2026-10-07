"""Outils read_report et edit_report: relire et modifier le rapport en apercu.

Une fois le rapport genere, le widget l'ouvre dans un panneau d'apercu, a
gauche de l'interface. L'utilisateur le lit et demande des changements a
Iris ("retire la figure 3", "simplifie le resume", "fais-le plutot pour
Guediawaye"); Iris:
  - lit le plan du rapport courant (read_report) pour savoir a quoi renvoie
    "le deuxieme paragraphe" ou "la carte";
  - demande la modification (edit_report): une nouvelle version est produite
    en arriere-plan, l'apercu se met a jour et surligne ce qui a change.

Le texte modifie passe par la meme verification que le premier jet (aucun
chiffre hors des faits, pas de certitude, reserves gardees); les textes fixes
(ANACIM, limites, methodologie) restent hors de portee du modele.
"""
from ..rapports import moteur_figures
from .common import ToolInputError

PERMISSION = "public"


def _gestionnaire(rapports):
    if rapports is None:
        raise ToolInputError("Les rapports ne sont pas disponibles ici.")
    return rapports


class ReadReport:
    NAME = "read_report"
    LABEL = "Lecture du rapport"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "Plan du RAPPORT affiche dans l'apercu (le plus recent de la conversation, ou "
        "report_id): version, demande comprise, paragraphes de chaque section, "
        "recommandations, visuels numerotes ('Figure 2', 'Tableau 1') et historique des "
        "versions. A appeler AVANT edit_report quand l'utilisateur designe un passage ou un "
        "visuel ('le deuxieme paragraphe', 'la carte', 'la derniere recommandation'), ou quand "
        "il pose une question sur le contenu du rapport."
    )
    SCHEMA = {"type": "object", "properties": {
        "report_id": {"type": "string", "description": "Omettre: rapport le plus recent."}}}

    @staticmethod
    def run(params, data, rapports=None, session_id=""):
        from ..rapports.taches import ModificationImpossible
        try:
            return _gestionnaire(rapports).lire(session_id, params.get("report_id"))
        except ModificationImpossible as exc:
            raise ToolInputError(str(exc))


class EditReport:
    NAME = "edit_report"
    LABEL = "Mise à jour du rapport"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "MODIFIE le rapport affiche dans l'apercu: produit une nouvelle version (meme rapport, "
        "apercu mis a jour, changements surlignes, fichiers PDF/Word/HTML regeneres). Combine "
        "au besoin: instruction (changement de TEXTE, en une phrase precise: 'raccourcir le "
        "resume executif', 'ajouter une recommandation sur l'information des quartiers', "
        "'reformuler le paragraphe sur l'exposition pour des elus'), changes (nouvelle zone, "
        "periode, phase, saison, public: memes champs que generate_report; les chiffres sont "
        "alors recalcules), remove_visuals (['Figure 2']), reference_figures / extra_figures "
        "(visuels a ajouter, comme pour generate_report), revert (true: revenir a la version "
        "precedente). Ne transmets que ce que l'utilisateur demande; n'ajoute jamais de "
        "chiffre a l'instruction. Si l'outil renvoie statut=question, pose cette question. Si "
        "statut=lance, dis en une phrase ce qui va changer: l'apercu se mettra a jour seul. Une "
        "demande qui enfreindrait les regles du rapport (chiffre absent des donnees, certitude, "
        "retrait des limites ou de la mention ANACIM) ne sera pas appliquee: explique pourquoi."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "report_id": {"type": "string", "description": "Omettre: rapport le plus recent."},
            "instruction": {"type": "string",
                            "description": "Changement de texte demande, reformule clairement."},
            "changes": {"type": "object", "description": "zone, zone_code, year_min, year_max, "
                        "phase, season, horizon, metric, audience, type."},
            "remove_visuals": {"type": "array", "items": {"type": "string"},
                               "description": "Etiquettes: 'Figure 2', 'Tableau 1'."},
            "reference_figures": {"type": "array", "items": {"type": "string"}},
            "extra_figures": {"type": "array", "items": {"type": "object"}},
            "revert": {"type": "boolean"},
        },
    }

    @staticmethod
    def run(params, data, rapports=None, session_id=""):
        from ..rapports.taches import ModificationImpossible
        for brute in params.get("extra_figures") or []:
            try:
                moteur_figures.Plan(brute)
            except moteur_figures.SpecInvalide as exc:
                raise ToolInputError("extra_figures: %s" % exc)
        try:
            r = _gestionnaire(rapports).modifier(session_id, params.get("report_id"), params)
        except ModificationImpossible as exc:
            raise ToolInputError(str(exc))
        if r.get("statut") == "question":
            return r
        r["consigne"] = ("La nouvelle version se prepare; l'apercu se mettra a jour et surlignera "
                         "les changements. Dis en une phrase ce qui va changer, sans chiffre.")
        return r


OUTILS = (ReadReport, EditReport)
