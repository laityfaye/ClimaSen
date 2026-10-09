"""Version des donnees: de quoi dater et retrouver chaque chiffre d'un rapport.

Le manifeste (outputs/manifest.json) liste les fichiers sources lus par les
rapports, avec leur empreinte sha256, leur source et leur periode, plus le
commit git du code. La "version des donnees" imprimee sur chaque page en est
derivee: deux rapports portant la meme version ont ete calcules sur les memes
fichiers, octet pour octet.

Il est ecrit par scripts/32_manifest_donnees.py (fin de pipeline, deploiement).
S'il est absent, on le calcule a la volee sans l'ecrire: un rapport ne doit
jamais sortir sans version.
"""
import datetime as dt
import hashlib
import json
import subprocess
import threading

from ..config import PROJECT_DIR

CHEMIN = PROJECT_DIR / "outputs" / "manifest.json"

# nom logique -> (chemin relatif, source, periode)
FICHIERS = {
    "evenements": ("data/processed/extreme_events_phases_senegal.csv",
                   "CHIRPS v2", "1981-2023"),
    "correlations_p1": ("outputs/teleconnections/correlations_Phase_1_debut.csv",
                        "CHIRPS v2 x NOAA OISST v2", "1983-2023"),
    "correlations_p2": ("outputs/teleconnections/correlations_Phase_2_pleine.csv",
                        "CHIRPS v2 x NOAA OISST v2", "1983-2023"),
    "correlations_p3": ("outputs/teleconnections/correlations_Phase_3_fin.csv",
                        "CHIRPS v2 x NOAA OISST v2", "1983-2023"),
    "correlations_toutes": ("outputs/teleconnections/correlations_Toutes phases.csv",
                            "CHIRPS v2 x NOAA OISST v2", "1983-2023"),
    "indices_sst": ("data/raw/climate_indices/daily_indices_all.csv",
                    "NOAA OISST v2", "1983-2023"),
    "clusters": ("outputs/clustering/All_phases/All_phases_cluster_characteristics.csv",
                 "NOAA OISST v2 (K-Means)", "1983-2023"),
    "etats_saisonniers": ("outputs/clustering_saisonnier/etats_saisonniers.json",
                          "NOAA OISST v2 (K-Means saisonnier)", "1983-2023"),
    "indice_departements": ("outputs/vulnerabilite/indice_risque_departements.csv",
                            "CHIRPS v2, ANSD RGPH-5, ANSD EHCVM", "1981-2023 / 2023"),
    "indice_arrondissements": ("outputs/vulnerabilite/indice_risque_arrondissements.csv",
                               "CHIRPS v2, ANSD RGPH-5, ANSD EHCVM", "1981-2023 / 2023"),
    "robustesse_indice": ("outputs/vulnerabilite/robustesse/resume.json",
                          "Inondations documentees 2005-2020", "2005-2020"),
    "communes": ("data/processed/correspondance_communes_arrondissements.csv",
                 "ANSD RGPH-5", "2023"),
    "ehcvm_services": ("data/raw/ansd/ehcvm_2021-2022_services_chocs_par_region.csv",
                       "ANSD EHCVM", "2021-2022"),
    "ehcvm_assainissement": ("data/raw/ansd/ehcvm_2021-2022_assainissement_par_region.csv",
                             "ANSD EHCVM", "2021-2022"),
    "ehcvm_pauvrete": ("data/raw/ansd/ehcvm_2021-2022_pauvrete_par_region.csv",
                       "ANSD EHCVM", "2021-2022"),
    "atlas_rgph5": ("data/raw/ansd/atlas_rgph5_2023_classes_extremes_departements.csv",
                    "ANSD Atlas RGPH-5", "2023"),
    "veille_competence": ("outputs/veille/competence_projection.json",
                          "Veille pre-saison", "1983-2023"),
    # Exposition et API SDMX de l'ANSD (scripts 33-37, 07-09/10/2026).
    "habitants_evenements": ("outputs/exposition_evenements/population_touchee_evenements.csv",
                             "ANSD RGPH-5 ; CHIRPS v2", "1981-2023 ; population 2023"),
    "habitants_projetes": ("outputs/exposition_evenements/population_touchee_projetee.csv",
                           "ANSD projections (API SDMX)", "2026-2030"),
    "communes_exposition": ("outputs/exposition_evenements/communes_reconstruites_controle.csv",
                            "ANSD RGPH-5 et coordonnees des localites", "2023"),
    "population_projetee": ("outputs/exposition_evenements/population_projetee_zones.csv",
                            "ANSD projections (API SDMX)", "2023-2030"),
    "pauvrete_ansd_sdmx": ("data/raw/ansd/odp/DF_TX_PAUV.csv",
                           "ANSD EHCVM et ESPS (API SDMX)", "2011-2022"),
    "zones_ansd": ("data/processed/correspondance_zones_ansd.csv",
                   "ANSD codes SDMX / OCHA P-codes", "2024"),
}

_verrou = threading.Lock()
_cache = {}


def _sha256(chemin) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def commit_git() -> str:
    try:
        sortie = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(PROJECT_DIR),
                                capture_output=True, text=True, timeout=5)
        if sortie.returncode == 0 and sortie.stdout.strip():
            return sortie.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "inconnu"


def calculer(racine=None) -> dict:
    """Manifeste des fichiers presents. Un fichier absent est note, pas omis."""
    racine = racine or PROJECT_DIR
    fichiers = {}
    for nom, (relatif, source, periode) in sorted(FICHIERS.items()):
        chemin = racine / relatif
        entree = {"chemin": relatif, "source": source, "periode": periode}
        if chemin.is_file():
            entree["sha256"] = _sha256(chemin)
            entree["octets"] = chemin.stat().st_size
        else:
            entree["sha256"] = None
        fichiers[nom] = entree
    empreinte = hashlib.sha256("".join(
        "%s=%s;" % (n, e["sha256"]) for n, e in sorted(fichiers.items())).encode()).hexdigest()
    commit = commit_git()
    return {
        "version": 1,
        "calcule_le": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit,
        "empreinte": empreinte,
        # Derivee des donnees seules: un commit qui ne touche que le code ne
        # change pas la version des donnees (le commit est imprime a part).
        "version_donnees": "D-%s" % empreinte[:10],
        "fichiers": fichiers,
        "absents": sorted(n for n, e in fichiers.items() if e["sha256"] is None),
    }


def ecrire(chemin=None) -> dict:
    manifeste = calculer()
    chemin = chemin or CHEMIN
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")
    with _verrou:
        _cache.clear()
    return manifeste


def lire() -> dict:
    """Manifeste ecrit par le script 32, sinon calcule (et garde en memoire)."""
    with _verrou:
        if "m" in _cache:
            return _cache["m"]
    manifeste = None
    if CHEMIN.is_file():
        try:
            manifeste = json.loads(CHEMIN.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifeste = None
    if not manifeste or "version_donnees" not in manifeste:
        manifeste = calculer()
        manifeste["note"] = "calcule a la volee (outputs/manifest.json absent)"
    with _verrou:
        _cache["m"] = manifeste
    return manifeste


def oublier() -> None:
    with _verrou:
        _cache.clear()
