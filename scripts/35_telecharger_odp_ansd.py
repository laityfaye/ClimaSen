#!/usr/bin/env python3
"""Telechargement des donnees de l'ANSD par son API SDMX (Open Data Platform).

L'ANSD a ouvert le 8 octobre 2026 sa plateforme de donnees (https://opendata.ansd.sn),
servie par un NSI web service SDMX. Ce script y lit, par requetes SDMX REST, les jeux
utiles a ClimatSen et les garde en copie datee dans data/raw/ansd/odp/ : la plateforme
est en version beta, et ClimatSen doit fonctionner meme si elle ne repond pas.

Jeux lus (agence SN1, format SDMX-CSV) :
  DF_PROJ_POP_2050_COM  population projetee 2023-2030, 553 communes
  DF_PROJ_POP_2050_DEP  population projetee 2023-2030, 46 departements
  DF_POP, DF_HOU, DF_CON  RGPH-5 2023 (population par sexe, menages, concessions),
                        de la region a la commune : la position "quartier" est fixee a
                        _T (total) pour ne pas telecharger les 25 225 quartiers et villages
  DF_TX_PAUV            taux, profondeur et severite de la pauvrete par region
                        (ESPS 2011, EHCVM 2018-19 et 2021-22)
  CL_REF_AREA           liste de codes des zones : seuls les niveaux region, departement
                        et commune sont gardes (le fichier complet pese 17 Mo)

MANIFEST.json donne pour chaque fichier la requete exacte, la date, le nombre de lignes et
l'empreinte sha256. Relance : les fichiers sont remplaces, et tout changement d'empreinte
est signale (l'ANSD a mis ses donnees a jour).

Usage : py -3 scripts/35_telecharger_odp_ansd.py
"""
import csv
import hashlib
import io
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "data" / "raw" / "ansd" / "odp"
NSI = "https://opendata.ansd.sn/admin/ws/nsi_ws/rest"
AGENCE = "SN1"
ACCEPT_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"

# nom du fichier -> (flux, cle SDMX, description)
JEUX = {
    "DF_PROJ_POP_2050_COM": ("DF_PROJ_POP_2050_COM", "all",
                             "Population projetée 2023-2030 par commune"),
    "DF_PROJ_POP_2050_DEP": ("DF_PROJ_POP_2050_DEP", "all",
                             "Population projetée 2023-2030 par département"),
    "DF_POP": ("DF_POP", "A10...._T..",
               "RGPH-5 2023 : population par sexe, de la région à la commune"),
    "DF_HOU": ("DF_HOU", "A10...._T..",
               "RGPH-5 2023 : ménages, de la région à la commune"),
    "DF_CON": ("DF_CON", "A10...._T..",
               "RGPH-5 2023 : concessions, de la région à la commune"),
    "DF_TX_PAUV": ("DF_TX_PAUV", "all",
                   "Pauvreté par région : taux, profondeur, sévérité (2011, 2019, 2022)"),
}
LISTE_ZONES = "CL_REF_AREA"
NS = {"s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
      "c": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"}
# Codes de zone de l'ANSD : SN-DK (region), SN-DK-PI (departement), SN-DK-PI1-1 (commune).
NIVEAUX = (("region", re.compile(r"SN-[A-Z]{2}")),
           ("departement", re.compile(r"SN-[A-Z]{2}-[A-Z]{2}")),
           ("commune", re.compile(r"SN-[A-Z]{2}-[A-Z]{2}\d+-\d+")))


def lire(url, accept=None, essais=4):
    """GET avec reprises : le service est en beta et coupe parfois la connexion."""
    entetes = {"User-Agent": "ClimatSen/1.0 (+https://climatsen.innosft.com)"}
    if accept:
        entetes["Accept"] = accept
    for k in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=entetes),
                                        timeout=300) as r:
                return r.read()
        except Exception as e:                      # noqa: BLE001
            if k == essais - 1:
                raise
            print(f"   reprise ({e})")
            time.sleep(5 * (k + 1))


def sha256(octets):
    return hashlib.sha256(octets).hexdigest()


def niveau(code):
    for nom, motif in NIVEAUX:
        if motif.fullmatch(code):
            return nom
    return None


def parent(code, niv):
    if niv == "departement":
        return code[:5]
    if niv == "commune":
        return code[:8]
    return "SN" if niv == "region" else None


def zones_csv(xml_octets):
    """Liste de codes CL_REF_AREA -> CSV code, nom, niveau, parent (region a commune)."""
    racine = ET.fromstring(xml_octets)
    tampon = io.StringIO()
    w = csv.writer(tampon, lineterminator="\n")
    w.writerow(["code", "nom", "niveau", "parent"])
    n = 0
    for code in racine.iter(f"{{{NS['s']}}}Code"):
        cid = code.get("id")
        niv = niveau(cid)
        if niv is None:
            continue
        noms = {e.get("{http://www.w3.org/XML/1998/namespace}lang"): e.text
                for e in code.findall("c:Name", NS)}
        w.writerow([cid, noms.get("fr") or noms.get("en") or "", niv, parent(cid, niv)])
        n += 1
    return tampon.getvalue().encode("utf-8"), n


def lire_manifeste(dossier=SORTIE):
    """{fichier: entree} du MANIFEST.json d'un dossier, vide s'il n'existe pas."""
    chemin = Path(dossier) / "MANIFEST.json"
    if not chemin.exists():
        return {}
    return {f["fichier"]: f for f in json.loads(chemin.read_text(encoding="utf-8"))["fichiers"]}


def telecharger(sortie=SORTIE):
    """Telecharge tous les jeux dans `sortie` et y ecrit MANIFEST.json.
    Renvoie la liste des entrees du manifeste. Leve une exception si l'API ne
    repond pas ou renvoie un jeu vide : rien n'est alors a considerer comme valide."""
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    maintenant = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fichiers = []
    for nom, (flux, cle, description) in JEUX.items():
        url = f"{NSI}/data/{AGENCE},{flux},1.0/{cle}/ALL/?dimensionAtObservation=AllDimensions"
        print(f"{nom} ...")
        octets = lire(url, ACCEPT_CSV)
        lignes = max(0, octets.count(b"\n") - 1)
        if lignes == 0 or octets.startswith(b"NoRecordsFound"):
            raise RuntimeError(f"{nom} : aucune donnee renvoyee par {url}")
        fichier = f"{nom}.csv"
        (sortie / fichier).write_bytes(octets)
        fichiers.append({"fichier": fichier, "flux": f"{AGENCE}:{flux}(1.0)",
                         "description": description, "requete": url, "format": "SDMX-CSV 1.0",
                         "lignes": lignes, "octets": len(octets), "sha256": sha256(octets),
                         "telecharge_le": maintenant})
        print(f"   {lignes} lignes, {len(octets) // 1024} Ko")

    url = f"{NSI}/codelist/{AGENCE}/{LISTE_ZONES}/1.0"
    print(f"{LISTE_ZONES} ...")
    octets, n = zones_csv(lire(url))
    if n == 0:
        raise RuntimeError(f"{LISTE_ZONES} : aucune zone dans {url}")
    fichier = "CL_REF_AREA_communes.csv"
    (sortie / fichier).write_bytes(octets)
    fichiers.append({"fichier": fichier, "flux": f"{AGENCE}:{LISTE_ZONES}(1.0)",
                     "description": "Zones de l'ANSD (région, département, commune) : code, "
                                    "nom, niveau, parent ; extrait de la liste de codes",
                     "requete": url, "format": "CSV extrait de SDMX-ML 2.1", "lignes": n,
                     "octets": len(octets), "sha256": sha256(octets),
                     "telecharge_le": maintenant})
    print(f"   {n} zones")

    manifeste = {
        "source": "ANSD, Open Data Platform (https://opendata.ansd.sn), API SDMX",
        "service": NSI,
        "licence": "Donnees publiques de l'ANSD : citer la source",
        "fichiers": fichiers,
    }
    (sortie / "MANIFEST.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fichiers


def fichiers_modifies(ancien, nouveau):
    """Noms des fichiers ajoutes, retires ou dont l'empreinte a change."""
    a = {f: e["sha256"] for f, e in ancien.items()}
    n = {e["fichier"]: e["sha256"] for e in nouveau}
    return sorted(f for f in set(a) | set(n) if a.get(f) != n.get(f))


def main():
    ancien = lire_manifeste()
    fichiers = telecharger(SORTIE)
    changes = fichiers_modifies(ancien, fichiers)
    if ancien and changes:
        print("Fichiers modifies depuis le dernier telechargement :", ", ".join(changes))
    print(f"OK : {len(fichiers)} fichiers dans {SORTIE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
