#!/usr/bin/env python3
"""Bulletin de veille pre-saison (a lancer chaque annee en avril).

Produit outputs/veille/bulletin_<annee>.json (lu par le dashboard et Jarvis)
et bulletin_<annee>.md (a diffuser aux acteurs operationnels).

Calendrier conseille:
  - des fevrier: --partiel, bulletin provisoire sur les mois deja observes;
  - fin avril: bulletin complet (etat novembre-avril + prevision C3S d'avril);
  - apres la saison: relancer pour ajouter la verification CHIRPS.

Avant chaque bulletin, mettre le cube SST a jour avec l'annee en cours:
    py -3 scripts/19_build_sst_cube.py --telecharger --annees <annee-1> <annee>

Usage:
    py -3 scripts/20_veille_presaison.py --annee 2027
    py -3 scripts/20_veille_presaison.py --annee 2027 --partiel
    py -3 scripts/20_veille_presaison.py --retro 2015 2023   # bulletins retrospectifs
    py -3 scripts/20_veille_presaison.py --competence        # recalcule la competence
    py -3 scripts/20_veille_presaison.py --annee 2027 --sans-c3s
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from veille import DOSSIER_SORTIE, production  # noqa: E402
from veille import c3s as mod_c3s  # noqa: E402


def _ascii(texte):
    """Le terminal Windows est en CP1252: rien d'exotique a l'ecran."""
    return texte.encode("ascii", "replace").decode("ascii")


def journal(texte):
    print(_ascii(texte), flush=True)


def annee_par_defaut():
    """La prochaine saison: l'annee en cours jusqu'en juin, la suivante ensuite."""
    aujourd_hui = dt.date.today()
    return aujourd_hui.year if aujourd_hui.month <= 6 else aujourd_hui.year + 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--annee", type=int, help="saison visee (defaut: la prochaine)")
    p.add_argument("--retro", type=int, nargs=2, metavar=("DEBUT", "FIN"),
                   help="bulletins retrospectifs sur une plage d'annees")
    p.add_argument("--partiel", action="store_true",
                   help="accepter un etat novembre-avril incomplet (bulletin provisoire)")
    p.add_argument("--sans-c3s", action="store_true", help="ne pas interroger Copernicus")
    p.add_argument("--competence", action="store_true",
                   help="recalculer la competence de la projection (plusieurs minutes)")
    args = p.parse_args()

    if args.competence:
        production.competence_projection(recalculer=True, journal=journal)
    avec_c3s = not args.sans_c3s
    if avec_c3s and not mod_c3s.cle_configuree():
        journal("[INFO] Cle Copernicus CDS absente (CDSAPI_KEY dans .env): bulletin sans C3S, "
                "niveau de risque indetermine.")
        avec_c3s = False

    if args.retro:
        annees = list(range(args.retro[0], args.retro[1] + 1))
    elif args.annee or not args.competence:
        annees = [args.annee or annee_par_defaut()]
    else:
        annees = []
    for annee in annees:
        journal("== Bulletin %d" % annee)
        b = production.produire(annee, avec_c3s=avec_c3s, partiel=args.partiel, journal=journal)
        n = b["niveau_risque"]
        journal("   niveau: %s | statut: %s | source: %s" % (n["libelle"], b["statut"], n["source"]))
        for a in b["avertissements"]:
            journal("   ! " + a)
        journal("   -> %s" % (DOSSIER_SORTIE / ("bulletin_%d.md" % annee)))


if __name__ == "__main__":
    main()
