"""Outil get_seasonal_outlook: le bulletin de veille pre-saison.

"L'annee prochaine sera-t-elle une annee d'inondations ?" Jarvis ne calcule
rien ici: il lit le bulletin produit hors ligne par
scripts/20_veille_presaison.py (outputs/veille/bulletin_<annee>.json), le
meme que la page "Veille" du dashboard.

Garde-fou central: la reponse porte TOUJOURS les competences mesurees et la
regle d'interpretation. Une probabilite sans sa fiabilite se lit comme une
certitude; ici, la projection oceanique n'a pas de competence demontree en
prevision reelle, et le modele doit le dire.
"""
from .common import ToolInputError, champ_entier

NAME = "get_seasonal_outlook"
LABEL = "Bulletin de veille pré-saison"
PERMISSION = "public"
DATASETS = ()

DESCRIPTION = (
    "Bulletin de VEILLE PRE-SAISON: risque que la saison des pluies d'une annee soit "
    "une ANNEE EXTREME (comme 1999, 2005, 2010, 2012, 2020, 2022, annees d'inondations). "
    "Donne le niveau de risque (faible/normal/eleve/tres eleve/indetermine), sa source "
    "(prevision saisonniere Copernicus C3S calibree sur CHIRPS), la projection de l'etat "
    "oceanique novembre-avril sur les configurations K-Means du memoire (indication "
    "EXPERIMENTALE), les annees analogues, la competence mesuree de chaque methode et, "
    "pour une saison passee, la verification. A utiliser pour 'l'annee prochaine sera-t-"
    "elle extreme', 'risque d'inondation cette saison', 'bulletin de veille'. Sans annee: "
    "le bulletin le plus recent. Rapporte toujours la competence et les avertissements; "
    "ne presente jamais la projection experimentale comme une prevision."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer",
                 "description": "Saison visee. Omettre pour le bulletin le plus recent."},
    },
}

REGLE = ("Le niveau de risque n'est calcule que par la prevision C3S calibree. Sans elle il "
         "est 'indetermine'. Tant que presentation.mode vaut 'probabilite' (competence C3S non "
         "demontree: AUC 0,59, p = 0,19), NE PAS annoncer de niveau (faible/eleve...): donner la "
         "probabilite indicative face a 33 % et dire que la competence n'est pas demontree. "
         "Le niveau ne s'annonce que si presentation.mode vaut 'niveau'. La probabilite de la projection oceanique est experimentale: "
         "sa competence en prevision reelle n'est pas demontree (voir competence_projection); "
         "la citer comme une indication, jamais comme une prevision. Frequence de reference "
         "d'une annee extreme: 1 sur 3.")


def run(params, data):
    from veille import production

    disponibles = production.bulletins_disponibles()
    if not disponibles:
        raise ToolInputError("Aucun bulletin de veille n'a encore ete produit.")
    annee = champ_entier(params, "year", mini=1981, maxi=2100)
    if annee is None:
        # Le plus recent = la saison la plus lointaine (bulletin prospectif).
        annee = disponibles[0]
    if annee not in disponibles:
        raise ToolInputError("Pas de bulletin pour %d. Bulletins disponibles: %s." % (
            annee, ", ".join(str(a) for a in sorted(disponibles))))
    b = production.lire_bulletin(annee)
    proj = b.get("projection") or {}
    return {
        "annee": b["annee"],
        "emis_le": b["emis_le"],
        "statut": b["statut"],
        "niveau_risque": b["niveau_risque"],
        "presentation": b.get("presentation"),
        "synthese": b["synthese"],
        "c3s": b.get("c3s"),
        "projection": {k: proj.get(k) for k in ("probabilite_experimentale", "configurations",
                                                "analogues", "annees_apprentissage")} if proj else None,
        "competence_projection": b.get("competence_projection"),
        "contexte": b.get("contexte"),
        "definition_annee_extreme": b.get("definition"),
        "verification": b.get("verification"),
        "avertissements": b.get("avertissements"),
        "regle_interpretation": REGLE,
        "bulletins_disponibles": sorted(disponibles),
        "source": "Veille pre-saison ClimatSen (outputs/veille/bulletin_%d.json)" % annee,
    }
