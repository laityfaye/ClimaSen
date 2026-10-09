#!/usr/bin/env python3
"""Verifie les donnees sources d'un serveur contre la reference du PC.

Les fichiers bruts CHIRPS .mat et OISST journalier ne sont pas dans git (trop
lourds pour GitHub ; le C3S y est depuis le 09/10/2026) :
on les telecharge ou on les copie sur le serveur. Ce script dit, source par
source, s'ils sont presents et IDENTIQUES a ceux qui ont produit les resultats
du memoire (taille + empreinte sha256). Une copie differente (NOAA revise
parfois ses fichiers) ne doit pas servir a relancer le pipeline sans
verification : les correlations publiees pourraient bouger.

Usage :
  py -3 scripts/39_verifier_sources.py --ecrire-reference   (sur le PC de reference)
  python3 scripts/39_verifier_sources.py                    (sur le serveur)
  python3 scripts/39_verifier_sources.py --rapide           (taille seulement)

Reference : outputs/sources_reference.json (versionne).
Code de sortie : 0 si tout ce qui est present est identique, 1 sinon.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = RACINE / "outputs" / "sources_reference.json"

# (groupe, motif relatif a la racine, role pour Iris et le pipeline)
SOURCES = [
    ("chirps_afrique_ouest", "data/raw/chirps_WA_1981_2023_dayly.mat",
     "pluie hors du Senegal (get_rainfall) ; script 01 (pipeline complet)"),
    ("oisst_journalier", "data/raw/SST/sst_day_anom_*.nc",
     "SST de n'importe quel jour (get_ocean_state), animation de tout evenement ; "
     "scripts 04, 11, 14, 17, 19"),
    ("c3s", "data/raw/c3s/*.nc", "veille pre-saison : scripts 20 et 21 [versionne]"),
    ("chirps_senegal", "data/processed/standardized_anomalies_senegal.npz",
     "pluie de tout jour sur le Senegal (get_rainfall) [versionne]"),
    ("chirps_senegal", "data/processed/climatology_senegal.npz",
     "normales et reconstruction de la pluie [versionne]"),
    ("ansd", "data/raw/ansd/rgph_repertoire_localites_1988-2023.csv",
     "population par recensement (get_locality) [versionne]"),
    ("ansd", "data/processed/localites_rgph5_placees.csv",
     "localites placees (get_locality, get_rainfall commune) [versionne]"),
    ("inondations", "data/raw/inondations/zones_touchees_2005_2009_2012_2020.csv",
     "inondations documentees (get_locality) [versionne]"),
]
# Produit derive : reconstruit par le script 19 a partir d'OISST, son empreinte
# change a chaque construction (archive compressee) ; on controle sa presence.
DERIVES = [("cube_sst_mensuel", "data/processed/sst_cube_1deg.npz",
            "mois de SST (get_ocean_state, veille) : py -3 scripts/19_build_sst_cube.py")]

BLOC = 8 * 1024 * 1024
# Git convertit les fins de ligne des fichiers texte (CRLF sous Windows, LF
# sous Linux) : on compare leur contenu en LF, sinon chaque CSV versionne
# paraitrait different sur le serveur.
TEXTE = {".csv", ".json", ".md", ".txt"}


def texte_normalise(chemin):
    return chemin.read_bytes().replace(b"\r\n", b"\n")


def taille(chemin):
    if chemin.suffix.lower() in TEXTE:
        return len(texte_normalise(chemin))
    return chemin.stat().st_size


def empreinte(chemin):
    if chemin.suffix.lower() in TEXTE:
        return hashlib.sha256(texte_normalise(chemin)).hexdigest()
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        while True:
            b = f.read(BLOC)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fichiers(motif):
    if any(c in motif for c in "*?["):
        return sorted(RACINE.glob(motif))
    p = RACINE / motif
    return [p] if p.is_file() else []


def relatif(p):
    return p.relative_to(RACINE).as_posix()


def inventaire(rapide):
    sortie = {}
    for groupe, motif, role in SOURCES:
        for p in fichiers(motif):
            e = {"groupe": groupe, "taille": taille(p)}
            if not rapide:
                e["sha256"] = empreinte(p)
            sortie[relatif(p)] = e
    return sortie


def ecrire_reference():
    debut = time.time()
    inv = inventaire(rapide=False)
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE.write_text(json.dumps({
        "ecrite_le": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "note": "fichiers sources qui ont produit les resultats publies",
        "fichiers": inv,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(e["taille"] for e in inv.values())
    print("Reference ecrite : %d fichiers, %.1f Go, %.0f s -> %s"
          % (len(inv), total / 1e9, time.time() - debut, relatif(REFERENCE)))
    return 0


def verifier(rapide):
    if not REFERENCE.is_file():
        print("Reference absente (%s) : la generer sur le PC avec --ecrire-reference."
              % relatif(REFERENCE))
        return 1
    ref = json.loads(REFERENCE.read_text(encoding="utf-8"))["fichiers"]
    differents = 0
    print("Reference : %d fichiers\n" % len(ref))
    for groupe, motif, role in SOURCES:
        attendus = [k for k, v in ref.items() if v["groupe"] == groupe
                    and Path(k).match(motif.split("/")[-1])]
        presents = {relatif(p): p for p in fichiers(motif)}
        ok, diff, manq = 0, [], []
        for k in attendus:
            p = presents.get(k)
            if p is None:
                manq.append(k)
                continue
            if taille(p) != ref[k]["taille"]:
                diff.append("%s (taille)" % Path(k).name)
            elif not rapide and empreinte(p) != ref[k]["sha256"]:
                diff.append("%s (contenu)" % Path(k).name)
            else:
                ok += 1
        en_trop = sorted(set(presents) - set(attendus))
        differents += len(diff)
        etat = ("ABSENT" if not presents else
                "DIFFERENT" if diff else
                "INCOMPLET" if manq else "IDENTIQUE")
        print("%-10s %-55s %d/%d" % (etat, motif, ok, len(attendus)))
        print("           -> %s" % role)
        for d in diff[:5]:
            print("           ! different : %s" % d)
        if manq and presents:
            print("           ! manquants : %s" % ", ".join(Path(m).name for m in manq[:6]))
        if en_trop:
            print("           + hors reference : %s" % ", ".join(Path(m).name for m in en_trop[:6]))
    for groupe, motif, role in DERIVES:
        etat = "PRESENT" if fichiers(motif) else "ABSENT"
        print("%-10s %-55s (derive)" % (etat, motif))
        print("           -> %s" % role)
    try:
        sys.path.insert(0, str(RACINE))
        from jarvis import sources
        print("\nCe que voit Iris :", json.dumps(sources.disponibilite(), ensure_ascii=True))
    except Exception as exc:                       # noqa: BLE001
        print("\n(jarvis.sources illisible : %s)" % exc)
    if rapide:
        print("\nMode rapide : tailles seulement, empreintes non verifiees.")
    if differents:
        print("\n%d fichier(s) different(s) de la reference : ne pas relancer le pipeline "
              "sur cette copie sans verifier l'impact sur les resultats." % differents)
    return 1 if differents else 0


def main():
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--ecrire-reference", action="store_true",
                         help="ecrire la reference a partir des fichiers de cette machine")
    parseur.add_argument("--rapide", action="store_true",
                         help="comparer les tailles seulement (pas d'empreinte)")
    args = parseur.parse_args()
    return ecrire_reference() if args.ecrire_reference else verifier(args.rapide)


if __name__ == "__main__":
    sys.exit(main())
