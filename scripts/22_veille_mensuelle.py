#!/usr/bin/env python3
"""Veille mensuelle: bulletin provisoire de la prochaine saison, de novembre a avril.

A lancer une fois par mois pendant la veille (debut de mois: NOAA publie
l'OISST avec deux a trois jours de retard). Enchaine:
  1. la saison visee: la prochaine saison des pluies (voir 20, annee_par_defaut);
  2. les mois de novembre (n-1) a avril (n) deja ecoules: ceux absents du
     cube sont telecharges (fichier NOAA de l'annee, qui s'allonge chaque
     jour) puis extraits;
  3. le bulletin, provisoire tant qu'avril n'est pas complet, avec le kit
     de scenario et la trajectoire mois par mois.

Hors de la periode de veille (mai a octobre), rien n'est telecharge: le
script le dit et s'arrete.

Usage:
    py -3 scripts/22_veille_mensuelle.py
    py -3 scripts/22_veille_mensuelle.py --sans-telechargement
"""
import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from veille import MOIS_ETAT, production  # noqa: E402
from veille import c3s as mod_c3s  # noqa: E402
from veille.cube import Cube, CubeIndisponible, construire  # noqa: E402


def _script(nom):
    spec = importlib.util.spec_from_file_location(nom.replace(".py", ""), RACINE / "scripts" / nom)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def journal(texte):
    print(texte.encode("ascii", "replace").decode("ascii"), flush=True)


def mois_ecoules(annee, aujourd_hui):
    """Mois de l'etat novembre-avril deja termines a la date donnee."""
    return [(annee + da, m) for da, m in MOIS_ETAT
            if dt.date(annee + da, m, 1) < aujourd_hui.replace(day=1)]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sans-telechargement", action="store_true",
                   help="ne pas telecharger: utiliser le cube tel quel")
    args = p.parse_args()

    aujourd_hui = dt.date.today()
    annee = _script("20_veille_presaison.py").annee_par_defaut()
    ecoules = mois_ecoules(annee, aujourd_hui)
    journal("Saison visee: %d | mois de veille ecoules: %s" % (
        annee, ", ".join("%02d/%d" % (m, a) for a, m in ecoules) or "aucun"))
    if not ecoules:
        journal("[INFO] La veille de la saison %d commence apres novembre %d: rien a faire."
                % (annee, annee - 1))
        return

    try:
        cube = Cube.charger()
        manquants = [m for m in ecoules if not cube.a_le_mois(*m)]
    except CubeIndisponible:
        manquants = list(ecoules)
    annees_a_extraire = sorted({a for a, _ in manquants})
    if annees_a_extraire and not args.sans_telechargement:
        cube19 = _script("19_build_sst_cube.py")
        for a in annees_a_extraire:
            cube19.telecharger(a)
    if annees_a_extraire:
        construire(annees_a_extraire, journal=journal)

    avec_c3s = mod_c3s.cle_configuree() and aujourd_hui >= dt.date(annee, 4, 15)
    b = production.produire(annee, avec_c3s=avec_c3s, partiel=True, journal=journal, kit=True)
    n = b["niveau_risque"]
    traj = (b.get("projection") or {}).get("trajectoire") or []
    journal("Bulletin %d: statut %s, niveau %s" % (annee, b["statut"], n["libelle"]))
    for t in traj:
        journal("  jusqu'a %s: indication %.2f, configuration C%d" % (
            t["jusqu_a"], t["probabilite_experimentale"], t["configuration"]))
    for a in b["avertissements"]:
        journal("  ! " + a)


if __name__ == "__main__":
    main()
