"""Jeux de donnees publies par l'API : description, sources et lecture.

Chaque jeu est mis sous une forme commune, une ligne par (zone, periode) :
    code     identifiant de la zone (P-code OCHA, ou "SN" pour le pays)
    periode  annee ("2023") ou jour ("2012-09-28")
    ...      colonnes descriptives (nom, departement, region...)
    <CODE>   une colonne par indicateur, nommee par son code SDMX
Cette forme sert a la fois les reponses JSON/CSV et les messages SDMX.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
VULNERABILITE = RACINE / "outputs" / "vulnerabilite"
EXPOSITION = RACINE / "outputs" / "exposition_evenements"
TRAITEES = RACINE / "data" / "processed"
# Codes de zone de l'ANSD (SDMX) <-> codes ClimatSen : scripts 35 et 36.
CORRESPONDANCE = TRAITEES / "correspondance_zones_ansd.csv"
# Population projetee par l'ANSD (2026, 2030) : script 37.
PROJ_ZONES = EXPOSITION / "population_projetee_zones.csv"
PROJ_EVENEMENTS = EXPOSITION / "population_touchee_projetee.csv"

LICENCE = {
    "nom": "CC BY 4.0",
    "url": "https://creativecommons.org/licenses/by/4.0/deed.fr",
    "attribution": "ClimatSen, d'après ANSD (RGPH-5 2023, EHCVM 2021-22), "
                   "OCHA (COD-AB 2024) et CHIRPS v2.0",
}

SOURCES = {
    "rgph5": {"nom": "ANSD, 5e Recensement général de la population et de l'habitat (RGPH-5), 2023, répertoire des localités",
              "url": "https://www.ansd.sn"},
    "rgph4": {"nom": "ANSD, RGPH-4, 2013, répertoire des localités",
              "url": "https://www.ansd.sn"},
    "localites": {"nom": "ANSD, coordonnées géographiques des localités (fichier transmis le 4 octobre 2026)",
                  "url": "https://www.ansd.sn"},
    "ehcvm": {"nom": "ANSD, Enquête harmonisée sur les conditions de vie des ménages (EHCVM) 2021-2022, taux de pauvreté régionaux",
              "url": "https://www.ansd.sn"},
    "ocha": {"nom": "OCHA, limites administratives du Sénégal (COD-AB, 2024), licence CC BY-IGO",
             "url": "https://data.humdata.org/dataset/cod-ab-sen"},
    "odp": {"nom": "ANSD, Open Data Platform, API SDMX (agence SN1) : projections de population 2023-2030 (DF_PROJ_POP_2050_COM, _DEP), pauvreté par région (DF_TX_PAUV) et codes de zone CL_REF_AREA",
            "url": "https://opendata.ansd.sn"},
    "chirps": {"nom": "UCSB Climate Hazards Center, CHIRPS v2.0, pluie journalière 0,25°, 1981-2023",
               "url": "https://www.chc.ucsb.edu/data/chirps"},
}

# code -> (libelle, unite). Le code sert de valeur a la dimension INDICATEUR
# en SDMX et de nom de colonne (en minuscules) en JSON et CSV.
INDICATEURS = {
    "POPULATION":              ("Population résidente (RGPH-5 2023)", "PERSONNES"),
    "POPULATION_2013":         ("Population résidente (RGPH-4 2013)", "PERSONNES"),
    "POPULATION_2026":         ("Population projetée par l'ANSD pour 2026", "PERSONNES"),
    "POPULATION_2030":         ("Population projetée par l'ANSD pour 2030", "PERSONNES"),
    "CROISSANCE_2013_2023":    ("Croissance de la population 2013-2023", "PCT"),
    "MENAGES":                 ("Ménages (RGPH-5 2023)", "MENAGES"),
    "SUPERFICIE":              ("Superficie", "KM2"),
    "DENSITE":                 ("Densité de population 2023", "HAB_KM2"),
    "TAUX_PAUVRETE_REGION":    ("Taux de pauvreté de la région (EHCVM 2021-22)", "PCT"),
    "PROFONDEUR_PAUVRETE_REGION": ("Profondeur de la pauvreté de la région (EHCVM 2021-22, API SDMX de l'ANSD)", "PCT"),
    "SEVERITE_PAUVRETE_REGION": ("Sévérité de la pauvreté de la région (EHCVM 2021-22, API SDMX de l'ANSD)", "PCT"),
    "PAUVRES_ESTIMES":         ("Personnes pauvres estimées (population 2023 × taux régional)", "PERSONNES"),
    "JOURS_EXTREMES":          ("Jours de pluie extrême par an (anomalie > +2 écarts-types, 1981-2023)", "JOURS_AN"),
    "JOURS_50MM":              ("Jours de pluie d'au moins 50 mm par an (1981-2023)", "JOURS_AN"),
    "ALEA":                    ("Composante aléa de l'indice (0 à 1)", "INDICE"),
    "EXPOSITION":              ("Composante exposition de l'indice (0 à 1)", "INDICE"),
    "VULNERABILITE":           ("Composante vulnérabilité de l'indice (0 à 1)", "INDICE"),
    "INDICE_RISQUE":           ("Indice de risque (moyenne géométrique aléa × exposition × vulnérabilité)", "INDICE"),
    "RANG":                    ("Rang national selon l'indice de risque (1 = le plus exposé)", "RANG"),
    "RANG_DANS_DEPARTEMENT":   ("Rang dans le département selon l'indice de risque", "RANG"),
    "NB_COMMUNES":             ("Nombre de communes (découpage 2023)", "NOMBRE"),
    "NB_LOCALITES":            ("Nombre de localités ANSD utilisées pour le contour", "NOMBRE"),
    "POPULATION_TOUCHEE":      ("Habitants de la zone de pluie extrême (RGPH-5 2023) ; pas un nombre de sinistrés", "PERSONNES"),
    "POPULATION_TOUCHEE_2026": ("Habitants de la zone de pluie extrême, population projetée par l'ANSD pour 2026", "PERSONNES"),
    "POPULATION_TOUCHEE_2030": ("Habitants de la zone de pluie extrême, population projetée par l'ANSD pour 2030", "PERSONNES"),
    "MENAGES_TOUCHES":         ("Ménages de la zone de pluie extrême (RGPH-5 2023)", "MENAGES"),
    "PART_POPULATION_NATIONALE": ("Part de la population nationale dans la zone de pluie extrême", "PCT"),
    "COUVERTURE":              ("Part de la grille couverte par la pluie extrême", "PCT"),
    "PLUIE_MAX":               ("Pluie journalière maximale sur la grille", "MM"),
    "PIXELS_EXTREMES":         ("Pixels CHIRPS en anomalie > +2 écarts-types", "PIXELS"),
    "DEPARTEMENTS_TOUCHES":    ("Départements ayant des habitants dans la zone de pluie extrême", "NOMBRE"),
    "POPULATION_DEPARTEMENT_LE_PLUS_TOUCHE": ("Habitants touchés dans le département le plus touché", "PERSONNES"),
    "NB_EVENEMENTS":           ("Nombre d'événements de pluie extrême", "NOMBRE"),
    "PERSONNES_EVENEMENTS":    ("Somme des habitants touchés sur les événements de l'année (une personne compte une fois par événement)", "PERSONNES"),
    "POPULATION_TOUCHEE_MAX":  ("Habitants touchés par l'événement le plus étendu de l'année", "PERSONNES"),
}

# Indicateurs dont la periode n'est pas celle de la ligne (2023 pour les zones).
ANNEE_INDICATEUR = {"POPULATION_2013": "2013", "POPULATION_2026": "2026",
                    "POPULATION_2030": "2030"}

UNITES = {
    "PERSONNES": "Personnes", "MENAGES": "Ménages", "KM2": "Kilomètres carrés",
    "HAB_KM2": "Habitants par kilomètre carré", "PCT": "Pourcentage",
    "JOURS_AN": "Jours par an", "MM": "Millimètres", "INDICE": "Indice sans unité (0 à 1)",
    "RANG": "Rang", "NOMBRE": "Nombre", "PIXELS": "Pixels de 0,25°",
}


@dataclass(frozen=True)
class Jeu:
    id: str
    flux: str                 # identifiant du flux SDMX (dataflow)
    titre: str
    description: str
    freq: str                 # "A" annuel, "D" journalier
    niveau: str               # niveau geographique des lignes
    fichiers: tuple
    sources: tuple
    script: str
    indicateurs: tuple
    lire: Callable[[], pd.DataFrame]
    avertissement: Optional[str] = None


def cle(nom) -> str:
    """Nom normalise pour les rapprochements : sans accents, ni espaces, ni
    ponctuation, en majuscules (M'BACKE et Mbacké donnent MBACKE)."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper())


# Noms de departements du fichier des localites de l'ANSD qui different du
# decoupage OCHA (memes alias que le script 33).
ALIAS_DEPARTEMENTS = {"KOUPENTOUM": "SN1203", "MEDINAYOROFOULAH": "SN0702",
                      "NIORO": "SN0503", "RANEROUFERLO": "SN0903"}


def _lire_csv(chemin):
    return pd.read_csv(chemin, encoding="utf-8")


def _departements():
    d = _lire_csv(VULNERABILITE / "indice_risque_departements.csv")
    out = pd.DataFrame({
        "code": d["pcode"], "periode": "2023", "nom": d["departement"],
        "code_ansd_sdmx": d["pcode"].map(codes_ansd_sdmx()),
        "region": d["region"], "code_region": d["pcode"].str[:4],
        "methode_alea": d["methode_alea"],
    })
    colonnes = {"POPULATION": "population_2023", "POPULATION_2013": "population_2013",
                "CROISSANCE_2013_2023": "croissance_2013_2023_pct", "MENAGES": "menages_2023",
                "SUPERFICIE": "superficie_km2", "DENSITE": "densite_2023_hab_km2",
                "TAUX_PAUVRETE_REGION": "taux_pauvrete_region_pct",
                "PAUVRES_ESTIMES": "pauvres_estimes_2023",
                "JOURS_EXTREMES": "jours_anomalie_2sigma_an", "JOURS_50MM": "jours_50mm_an",
                "ALEA": "A_alea", "EXPOSITION": "E_exposition",
                "VULNERABILITE": "V_vulnerabilite", "INDICE_RISQUE": "indice_risque",
                "RANG": "rang"}
    for code, col in colonnes.items():
        out[code] = d[col]
    out = _avec_pauvrete(_avec_projection(out))
    return out.sort_values("RANG").reset_index(drop=True)


def _arrondissements():
    a = _lire_csv(VULNERABILITE / "indice_risque_arrondissements.csv")
    out = pd.DataFrame({
        "code": a["pcode"], "periode": "2023", "nom": a["arrondissement"],
        "departement": a["departement"], "code_departement": a["adm2_pcode"],
        "region": a["region"], "code_region": a["adm2_pcode"].str[:4],
        "methode_alea": a["methode_alea"],
    })
    colonnes = {"POPULATION": "population_2023", "POPULATION_2013": "population_2013",
                "CROISSANCE_2013_2023": "croissance_2013_2023_pct", "MENAGES": "menages_2023",
                "NB_COMMUNES": "n_communes_2023",
                "SUPERFICIE": "superficie_km2", "DENSITE": "densite_2023_hab_km2",
                "TAUX_PAUVRETE_REGION": "taux_pauvrete_region_pct",
                "PAUVRES_ESTIMES": "pauvres_estimes_2023",
                "JOURS_EXTREMES": "jours_anomalie_2sigma_an", "JOURS_50MM": "jours_50mm_an",
                "ALEA": "A_alea", "EXPOSITION": "E_exposition",
                "VULNERABILITE": "V_vulnerabilite", "INDICE_RISQUE": "indice_risque",
                "RANG": "rang", "RANG_DANS_DEPARTEMENT": "rang_dans_departement"}
    for code, col in colonnes.items():
        out[code] = a[col]
    for code in ("RANG", "RANG_DANS_DEPARTEMENT", "NB_COMMUNES"):
        out[code] = out[code].astype("Int64")
    out = _avec_pauvrete(out)
    return out.sort_values("RANG").reset_index(drop=True)


def code_commune(adm2_pcode, nom_ansd) -> str:
    """Identifiant stable d'une commune : P-code du departement + nom ANSD.

    Le code ANSD (COD_ENTITE) ne suffit pas : il est partage par deux
    communes de Podor dans le fichier des localites, et une commune a
    cheval sur deux departements y apparait deux fois."""
    return "%s_%s" % (adm2_pcode, cle(nom_ansd))


def _communes():
    geo = geojson_communes()
    lignes = [f["properties"] for f in geo["features"]]
    c = pd.DataFrame(lignes)
    out = pd.DataFrame({
        "code": c["code"], "periode": "2023", "nom": c["commune_ansd"],
        "code_ansd": c["cod_entite"].astype("Int64"),
        "code_ansd_sdmx": c["code"].map(codes_ansd_sdmx()),
        "departement": c["departement"], "code_departement": c["adm2_pcode"],
        "region": c["region"], "code_region": c["adm2_pcode"].str[:4],
        "part_dans_departement": c["part_dans_departement"],
    })
    colonnes = {"POPULATION": "population_2023", "MENAGES": "menages_2023",
                "SUPERFICIE": "superficie_km2", "DENSITE": "densite_hab_km2",
                "JOURS_EXTREMES": "jours_extremes_par_an", "NB_LOCALITES": "localites"}
    for code, col in colonnes.items():
        out[code] = c[col]
    out = _avec_projection(out)
    return out.sort_values(["code_departement", "nom"]).reset_index(drop=True)


def _avec_pauvrete(out):
    """Profondeur et severite de la pauvrete de la region (2022), lues par l'API
    SDMX de l'ANSD (DF_TX_PAUV, script 35). Descriptives : hors de l'indice."""
    odp = RACINE / "data" / "raw" / "ansd" / "odp" / "DF_TX_PAUV.csv"
    vals = {}
    if odp.exists() and CORRESPONDANCE.exists():
        p = pd.read_csv(odp, sep=None, engine="python", dtype=str)
        c = pd.read_csv(CORRESPONDANCE, dtype=str)
        region = dict(zip(c["code_ansd"], c["code_climatsen"]))
        p = p[p["TIME_PERIOD"] == "2022"]
        for r in p.itertuples():
            vals.setdefault(r.TX_PAUV, {})[region.get(r.REF_AREA)] = float(r.OBS_VALUE)
    for ind, code in (("PROFONDEUR_PAUVRETE_REGION", "P_PAUV"),
                      ("SEVERITE_PAUVRETE_REGION", "S_PAUV")):
        out[ind] = out["code_region"].map(vals.get(code, {}))
    return out


def _avec_projection(out):
    """Ajoute la population projetee par l'ANSD (2026, 2030) a une table de
    zones ; colonnes vides si le script 37 n'a pas tourne."""
    proj = (pd.read_csv(PROJ_ZONES).set_index("code") if PROJ_ZONES.exists()
            else pd.DataFrame())
    for a in (2026, 2030):
        col = f"population_{a}"
        out[f"POPULATION_{a}"] = out["code"].map(proj[col]) if col in proj else float("nan")
    return out


def _evenements():
    e = _lire_csv(EXPOSITION / "population_touchee_evenements.csv")
    codes = {cle(n): p for p, n in zip(*_noms_departements())}
    codes.update(ALIAS_DEPARTEMENTS)
    plus = e["departement_le_plus_touche"]
    out = pd.DataFrame({
        "code": "SN", "periode": e["date"], "phase": e["phase"],
        "departement_le_plus_touche": plus,
        "code_departement_le_plus_touche": [codes.get(cle(n)) if isinstance(n, str) else None
                                            for n in plus],
    })
    colonnes = {"POPULATION_TOUCHEE": "population_touchee_2023",
                "MENAGES_TOUCHES": "menages_touches_2023",
                "PART_POPULATION_NATIONALE": "part_population_nationale_pct",
                "COUVERTURE": "couverture_pct", "PLUIE_MAX": "pluie_max_mm",
                "PIXELS_EXTREMES": "pixels_extremes",
                "DEPARTEMENTS_TOUCHES": "departements_touches",
                "POPULATION_DEPARTEMENT_LE_PLUS_TOUCHE": "population_departement_le_plus_touche"}
    for code, col in colonnes.items():
        out[code] = e[col]
    proj = (pd.read_csv(PROJ_EVENEMENTS).set_index("date") if PROJ_EVENEMENTS.exists()
            else pd.DataFrame())
    for a in (2026, 2030):
        col = f"population_touchee_{a}"
        out[f"POPULATION_TOUCHEE_{a}"] = (out["periode"].map(proj[col])
                                          if col in proj else float("nan"))
    return out.sort_values("periode").reset_index(drop=True)


def _annees():
    a = _lire_csv(EXPOSITION / "population_touchee_par_annee.csv")
    return pd.DataFrame({
        "code": "SN", "periode": a["annee"].astype(str),
        "NB_EVENEMENTS": a["evenements"],
        "PERSONNES_EVENEMENTS": a["personnes_evenements"],
        "POPULATION_TOUCHEE_MAX": a["evenement_max"],
    })


AVERTISSEMENT_INDICE = (
    "Validation sur les inondations documentées (2005, 2009, 2012, 2020) : AUC 0,49 "
    "pour l'indice composite, 0,84 pour l'exposition seule. Le classement sert à "
    "comparer les zones, pas à prédire un sinistre.")
AVERTISSEMENT_TOUCHEE = (
    "Habitants recensés en 2023 dans les pixels où la pluie a dépassé +2 écarts-types "
    "ce jour-là : ce n'est pas un nombre de sinistrés.")

JEUX = {j.id: j for j in (
    Jeu("departements", "DF_RISQUE_DEPARTEMENTS",
        "Indice de risque de pluie extrême par département",
        "Aléa (fréquence des pluies extrêmes 1981-2023), exposition (population RGPH-5 2023) "
        "et vulnérabilité (pauvreté EHCVM 2021-22) des 46 départements.",
        "A", "departement",
        (VULNERABILITE / "indice_risque_departements.csv",),
        ("rgph5", "rgph4", "ehcvm", "odp", "ocha", "chirps"), "scripts/26_indice_risque_departements.py, 37",
        ("POPULATION", "POPULATION_2026", "POPULATION_2030", "POPULATION_2013",
         "CROISSANCE_2013_2023", "MENAGES", "SUPERFICIE",
         "DENSITE", "TAUX_PAUVRETE_REGION", "PROFONDEUR_PAUVRETE_REGION",
         "SEVERITE_PAUVRETE_REGION", "PAUVRES_ESTIMES", "JOURS_EXTREMES", "JOURS_50MM",
         "ALEA", "EXPOSITION", "VULNERABILITE", "INDICE_RISQUE", "RANG"),
        _departements, AVERTISSEMENT_INDICE),
    Jeu("arrondissements", "DF_RISQUE_ARRONDISSEMENTS",
        "Indice de risque de pluie extrême par arrondissement",
        "Même indice que pour les départements, calculé sur les 125 arrondissements "
        "(communes du RGPH-5 rattachées aux arrondissements OCHA).",
        "A", "arrondissement",
        (VULNERABILITE / "indice_risque_arrondissements.csv",),
        ("rgph5", "rgph4", "ehcvm", "odp", "ocha", "chirps"), "scripts/27 à 31, 35",
        ("POPULATION", "POPULATION_2013", "CROISSANCE_2013_2023", "MENAGES", "NB_COMMUNES",
         "SUPERFICIE", "DENSITE", "TAUX_PAUVRETE_REGION", "PROFONDEUR_PAUVRETE_REGION",
         "SEVERITE_PAUVRETE_REGION", "PAUVRES_ESTIMES", "JOURS_EXTREMES",
         "JOURS_50MM", "ALEA", "EXPOSITION", "VULNERABILITE", "INDICE_RISQUE", "RANG",
         "RANG_DANS_DEPARTEMENT"),
        _arrondissements, AVERTISSEMENT_INDICE),
    Jeu("communes", "DF_EXPOSITION_COMMUNES",
        "Population et pluies extrêmes par commune",
        "552 communes du découpage actuel : population et ménages RGPH-5 2023, superficie "
        "et densité sur des contours reconstruits à partir des coordonnées des localités "
        "transmises par l'ANSD, jours de pluie extrême par an.",
        "A", "commune",
        (TRAITEES / "communes_reconstruites_ansd.geojson",),
        ("rgph5", "localites", "odp", "ocha", "chirps"), "scripts/34_communes_reconstruites.py, 37",
        ("POPULATION", "POPULATION_2026", "POPULATION_2030", "MENAGES", "SUPERFICIE", "DENSITE",
         "JOURS_EXTREMES", "NB_LOCALITES"),
        _communes,
        "Contours approximatifs (polygones de Voronoï des localités, IoU médiane 0,78 avec "
        "GADM) : superficie et densité sont des estimations. Une commune à cheval sur deux "
        "départements apparaît une fois par département."),
    Jeu("evenements", "DF_EVENEMENTS",
        "Événements de pluie extrême et habitants de la zone touchée",
        "Les 1 317 journées de pluie extrême détectées sur 1981-2023 (CHIRPS), avec les "
        "habitants (RGPH-5 2023) des pixels en anomalie > +2 écarts-types.",
        "D", "pays",
        (EXPOSITION / "population_touchee_evenements.csv",),
        ("chirps", "rgph5", "localites", "odp", "ocha"), "scripts/33_population_touchee_evenements.py, 37",
        ("POPULATION_TOUCHEE", "POPULATION_TOUCHEE_2026", "POPULATION_TOUCHEE_2030",
         "MENAGES_TOUCHES", "PART_POPULATION_NATIONALE", "COUVERTURE",
         "PLUIE_MAX", "PIXELS_EXTREMES", "DEPARTEMENTS_TOUCHES",
         "POPULATION_DEPARTEMENT_LE_PLUS_TOUCHE"),
        _evenements, AVERTISSEMENT_TOUCHEE),
    Jeu("annees", "DF_EVENEMENTS_ANNUELS",
        "Événements de pluie extrême et habitants touchés par année",
        "Agrégation annuelle 1981-2023 du jeu « evenements ».",
        "A", "pays",
        (EXPOSITION / "population_touchee_par_annee.csv",),
        ("chirps", "rgph5", "localites", "ocha"), "scripts/33_population_touchee_evenements.py",
        ("NB_EVENEMENTS", "PERSONNES_EVENEMENTS", "POPULATION_TOUCHEE_MAX"),
        _annees, AVERTISSEMENT_TOUCHEE),
)}


# --- cache --------------------------------------------------------------------
# Les fichiers ne changent qu'au deploiement. On relit quand meme un fichier
# dont la date de modification a change, pour ne jamais servir un etat perime.
_cache = {}
_verrou = Lock()


def _empreinte(fichiers):
    return tuple(Path(f).stat().st_mtime_ns for f in fichiers)


def _memo(cle_cache, fichiers, calcul):
    empreinte = _empreinte(fichiers)
    with _verrou:
        trouve = _cache.get(cle_cache)
        if trouve and trouve[0] == empreinte:
            return trouve[1]
    valeur = calcul()
    with _verrou:
        _cache[cle_cache] = (empreinte, valeur)
    return valeur


def disponible(jeu: Jeu) -> bool:
    return all(Path(f).exists() for f in jeu.fichiers)


def table(jeu_id: str) -> pd.DataFrame:
    jeu = JEUX[jeu_id]
    fichiers = jeu.fichiers
    if jeu_id in ("departements", "arrondissements", "communes"):
        pauvrete = RACINE / "data" / "raw" / "ansd" / "odp" / "DF_TX_PAUV.csv"
        fichiers = fichiers + tuple(f for f in (CORRESPONDANCE, PROJ_ZONES, pauvrete)
                                    if f.exists())
    if jeu_id == "evenements" and PROJ_EVENEMENTS.exists():
        fichiers = fichiers + (PROJ_EVENEMENTS,)
    if jeu_id == "evenements":
        fichiers = fichiers + (VULNERABILITE / "indice_risque_departements.csv",)
    return _memo(("table", jeu_id), fichiers, jeu.lire)


def codes_ansd_sdmx() -> dict:
    """Code ClimatSen -> code(s) de zone de l'ANSD (SDMX, liste CL_REF_AREA).
    Une commune decoupee en 2023 (Keur Massar) en a deux, joints par « + »,
    comme une requete SDMX. Vide si la table du script 36 manque."""
    if not CORRESPONDANCE.exists():
        return {}

    def lire():
        t = pd.read_csv(CORRESPONDANCE, dtype=str).dropna(subset=["code_climatsen"])
        return {k: "+".join(sorted(g)) for k, g in t.groupby("code_climatsen")["code_ansd"]}
    return _memo(("codes_ansd",), (CORRESPONDANCE,), lire)


def _noms_departements():
    d = _lire_csv(VULNERABILITE / "indice_risque_departements.csv")
    return list(d["pcode"]), list(d["departement"])


# --- contours -----------------------------------------------------------------
CONTOURS = {
    "departements": TRAITEES / "contours_admin2_simplifies.geojson",
    "arrondissements": TRAITEES / "contours_admin3_simplifies.geojson",
    "communes": TRAITEES / "communes_reconstruites_ansd.geojson",
}


def geojson_communes():
    def lire():
        geo = json.loads(CONTOURS["communes"].read_text(encoding="utf-8"))
        for f in geo["features"]:
            p = f["properties"]
            p["code"] = code_commune(p["adm2_pcode"], p["commune_ansd"])
        return geo
    return _memo(("geo", "communes"), (CONTOURS["communes"],), lire)


def geojson(niveau: str) -> dict:
    """Contours d'un niveau, avec les indicateurs du jeu correspondant dans
    les proprietes : un seul fichier suffit pour une carte dans QGIS."""
    chemin = CONTOURS[niveau]

    def lire():
        if niveau == "communes":
            geo = json.loads(json.dumps(geojson_communes()))
        else:
            geo = json.loads(chemin.read_text(encoding="utf-8"))
        t = table(niveau).set_index("code")
        for f in geo["features"]:
            p = f["properties"]
            code = p.get("code") or p.get("pcode")
            ligne = t.loc[code] if code in t.index else None
            props = {"code": code}
            if ligne is not None:
                props.update(ligne_vers_dict(ligne, avec_code=False))
            f["properties"] = props
        return geo
    return _memo(("geojson", niveau), (chemin,) + JEUX[niveau].fichiers, lire)


def ligne_vers_dict(ligne, avec_code=True) -> dict:
    """Une ligne de table en dictionnaire JSON : indicateurs en minuscules,
    valeurs manquantes en null, entiers rendus comme entiers."""
    out = {}
    for k, v in ligne.items():
        if k == "code" and not avec_code:
            continue
        out[k.lower() if k in INDICATEURS else k] = valeur_json(v)
    if avec_code and "code" not in out and getattr(ligne, "name", None) is not None:
        out["code"] = ligne.name
    return out


def valeur_json(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        return int(v)
    return v


def zones() -> list:
    """Liste de codes de la dimension REF_AREA, du pays aux communes, avec
    leur parent : c'est la liste de codes hierarchique CL_ZONE."""
    ansd = codes_ansd_sdmx()
    out = [{"id": "SN", "nom": "Sénégal", "niveau": "pays", "parent": None}]
    d = table("departements")
    for code, nom in sorted(set(zip(d["code_region"], d["region"]))):
        out.append({"id": code, "nom": nom, "niveau": "region", "parent": "SN"})
    for _, r in d.sort_values("code").iterrows():
        out.append({"id": r["code"], "nom": r["nom"], "niveau": "departement",
                    "parent": r["code_region"]})
    for jeu, niveau in (("arrondissements", "arrondissement"), ("communes", "commune")):
        t = table(jeu)
        for _, r in t.sort_values("code").iterrows():
            z = {"id": r["code"], "nom": r["nom"], "niveau": niveau,
                 "parent": r["code_departement"]}
            if niveau == "commune" and not pd.isna(r["code_ansd"]):
                z["code_ansd"] = int(r["code_ansd"])
            out.append(z)
    for z in out:
        if z["id"] in ansd:
            z["code_ansd_sdmx"] = ansd[z["id"]]
    return out
