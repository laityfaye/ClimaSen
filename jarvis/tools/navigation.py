"""Outil navigate_dashboard: Jarvis ouvre une page du dashboard et y regle
les filtres.

Jusqu'ici Jarvis LISAIT la page affichee (Phase 7). Cet outil lui permet
de la CHANGER: "montre-moi les teleconnexions de pleine saison" ouvre la
page Teleconnexions, phase pleine saison. C'est la brique du mode
soutenance.

Securite: la demande passe par le meme validateur que le contexte de page
(jarvis/page_context.py): pages et filtres en liste fermee, valeurs
enumerees ou bornees. Rien d'autre n'atteint le navigateur. L'outil ne
touche a rien cote serveur: il renvoie une consigne de navigation que
l'application relaie au widget (evenement "navigation"), qui l'applique au
dashboard de l'utilisateur, et de lui seul.
"""
from .common import ToolInputError

NAME = "navigate_dashboard"
LABEL = "Navigation dans le dashboard"
PERMISSION = "public"
DATASETS = ()

# Copie des pages et filtres de jarvis/page_context.py (CHAMPS). Pas d'import
# au chargement: page_context importe jarvis.tools, qui importe ce module --
# import circulaire au demarrage du serveur (constate). La validation, elle,
# passe bien par page_context (import dans run); un test verifie que cette
# copie reste identique a CHAMPS.
FILTRES = {
    "Evenements": ("annees", "phases", "evenement_date"),
    "Indices SST": ("indices", "agregation"),
    "Teleconnexions": ("phase", "metrique", "type_correlation",
                       "significatives_seulement", "p_value", "phase_lag0",
                       "indices_series"),
    "Clustering": ("phase", "cluster", "metrique_barres"),
    "Pipeline": ("onglet",),
}
PAGES = tuple(FILTRES)

DESCRIPTION = (
    "OUVRE une page du dashboard sur l'ecran de l'utilisateur et y regle des "
    "filtres. A utiliser quand l'utilisateur demande de montrer, d'ouvrir ou "
    "d'aller sur une page ou une vue du dashboard, ou pour accompagner une "
    "explication de la vue correspondante. Filtres acceptes par page -- "
    + "; ".join("%s: %s" % (p, ", ".join(f)) for p, f in FILTRES.items())
    + ". Valeurs: phases Phase_1_debut, "
    "Phase_2_pleine, Phase_3_fin (Toutes phases, ou All_phases pour le "
    "Clustering); indices SST en noms courts (AMO, TNA...); annees = "
    "[debut, fin]. Un filtre invalide est ignore et signale."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "page": {"type": "string", "enum": list(PAGES),
                 "description": "Page a ouvrir."},
        "filters": {"type": "object",
                    "description": "Filtres a regler sur cette page (optionnel)."},
    },
    "required": ["page"],
}


def run(params, data):
    from .. import page_context
    page = params.get("page")
    if page not in page_context.CHAMPS:
        raise ToolInputError("page inconnue: %r. Valeurs acceptees: %s."
                             % (page, ", ".join(page_context.PAGES)))
    demandes = params.get("filters") or {}
    if not isinstance(demandes, dict):
        raise ToolInputError("filters doit etre un objet {nom: valeur}.")
    propre = page_context.nettoyer({"page": page, "filtres": demandes}) or {
        "page": page, "filtres": {}}
    ignores = sorted(set(demandes) - set(propre["filtres"]))
    resultat = {
        "navigation": {"page": page, "filtres": propre["filtres"]},
        "effectuee": True,
        "consigne": ("La page s'ouvre sur l'ecran de l'utilisateur. Ne decris "
                     "pas l'interface: dis ce qu'il va y voir d'important."),
    }
    if ignores:
        attendus = {nom: libelle for nom, (_, libelle)
                    in page_context.CHAMPS[page].items()}
        resultat["filtres_ignores"] = ignores
        resultat["filtres_acceptes_sur_cette_page"] = attendus
    return resultat
