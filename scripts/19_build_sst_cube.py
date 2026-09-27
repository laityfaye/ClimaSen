#!/usr/bin/env python3
"""Cube SST compact de la veille pre-saison (1 deg, 60S-60N).

Extrait des fichiers OISST annuels (data/raw/SST, ~1,5 Go chacun) les
moyennes mensuelles et les champs des jours d'evenements extremes, vers
data/processed/sst_cube_1deg.npz (~80 Mo). Incremental: seules les annees
demandees sont relues.

Usage:
    py -3 scripts/19_build_sst_cube.py                    # 1983-2023 (complet, ~7 min)
    py -3 scripts/19_build_sst_cube.py --annees 2024 2025
    py -3 scripts/19_build_sst_cube.py --telecharger --annees 2026
        (re)telecharge d'abord le fichier NOAA: indispensable pour l'annee en
        cours, dont le fichier s'allonge chaque mois.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from veille import CUBE_SST  # noqa: E402
from veille.cube import DOSSIER_OISST, CubeIndisponible, construire  # noqa: E402


def telecharger(annee):
    """Telecharge le fichier NOAA de l'annee (remplace un fichier existant)."""
    spec = importlib.util.spec_from_file_location(
        "download_sst_noaa", RACINE / "scripts" / "download_sst_noaa.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    final = DOSSIER_OISST / module.local_name(annee)
    neuf = final.with_name(final.stem + "_neuf.nc")
    DOSSIER_OISST.mkdir(parents=True, exist_ok=True)
    print("[INFO] Telechargement OISST %d..." % annee)
    res = module.download_file(annee, neuf)
    if not res.get("ok"):
        raise SystemExit("[ERREUR] Telechargement %d: %s" % (annee, res.get("msg")))
    neuf.replace(final)
    print("[OK] %s (%.0f Mo)" % (final.name, res.get("size_mb", 0)))


def main():
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--annees", type=int, nargs="+",
                         help="annees a (re)extraire (defaut: 1983-2023)")
    parseur.add_argument("--telecharger", action="store_true",
                         help="(re)telecharger d'abord les fichiers NOAA de ces annees")
    args = parseur.parse_args()
    annees = args.annees or list(range(1983, 2024))
    if args.telecharger:
        for a in annees:
            telecharger(a)
    try:
        cube = construire(annees)
    except CubeIndisponible as exc:
        raise SystemExit("[ERREUR] %s" % exc)
    a, m = cube.dernier_mois()
    print("[OK] %s: %d mois (dernier %02d/%d), %d evenements, %.0f Mo" % (
        CUBE_SST.name, len(cube.mois), m, a, len(cube.evt_dates), CUBE_SST.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
