"""Outil get_pipeline_status: etat de la chaine de traitement (Phase 7).

Meme liste d'etapes que le module "Pipeline" du dashboard
(scripts/vues/pipeline.py, PIPELINE_STEPS): une seule source de verite, une
etape ajoutee au dashboard apparait ici sans rien toucher.

Pour chaque etape: ses sorties existent-elles, de quand datent-elles, et
surtout sont-elles PLUS ANCIENNES que celles des etapes dont elle depend ? Une
figure de teleconnexions produite avant la derniere detection des evenements
decrit un catalogue qui n'existe plus: c'est l'incoherence la plus facile a
commettre et la plus difficile a voir a l'oeil.

Ne renvoie que des chemins RELATIFS au projet et des dates: rien sur
l'organisation du serveur.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .common import ToolInputError

NAME = "get_pipeline_status"
LABEL = "État du pipeline de traitement"
PERMISSION = "public"
DATASETS = ("pipeline",)

# Qui lit la sortie de qui, releve dans les scripts eux-memes (fichiers lus).
# Une etape absente de cette table n'a pas d'amont dans le pipeline.
DEPENDANCES = {
    "02": ["01"],
    "03": ["01"],
    "03b": ["03"],
    "04": ["01", "sst"],
    "11": ["01"],
    "14": ["11"],
    "19": ["01"],
    "20": ["01", "19"],
    "26": ["01"],
    "27": ["26"],
    "29": ["26", "27"],
    "33": ["01"],
    "34": ["33"],
    "36": ["35"],
    "37": ["33", "36"],
}

# Etapes posterieures a la liste de la page Pipeline (30/09-09/10/2026) :
# indice de risque, exposition, donnees de l'ANSD. Elles ne sont PAS ajoutees a
# la page, dont le bouton "pipeline complet" les lancerait (35 telecharge depuis
# l'ANSD) ; seul cet outil les surveille. Un id deja present dans la page
# l'emporte sur celui-ci.
ETAPES_COMPLEMENTAIRES = [
    {"id": "26", "num": 26, "label": "Indice de risque par departement",
     "script": "26_indice_risque_departements.py", "category": "Vulnerabilite",
     "outputs": ["outputs/vulnerabilite/indice_risque_departements.csv"],
     "exports": {"data": [{"path": "outputs/vulnerabilite/resume.json"}]}},
    {"id": "27", "num": 27, "label": "Indice de risque par arrondissement",
     "script": "27_indice_risque_arrondissements.py", "category": "Vulnerabilite",
     "outputs": ["outputs/vulnerabilite/indice_risque_arrondissements.csv"],
     "exports": {"data": [{"path": "outputs/vulnerabilite/resume_arrondissements.json"}]}},
    {"id": "29", "num": 29, "label": "Robustesse et validation de l'indice",
     "script": "29_robustesse_indice.py", "category": "Vulnerabilite",
     "outputs": ["outputs/vulnerabilite/robustesse/resume.json"],
     "exports": {"data": [{"path": "outputs/vulnerabilite/robustesse/validation_auc_departements.csv"}]}},
    {"id": "33", "num": 33, "label": "Habitants des zones touchees par evenement",
     "script": "33_population_touchee_evenements.py", "category": "Exposition",
     "outputs": ["outputs/exposition_evenements/population_touchee_evenements.csv"],
     "exports": {"data": [{"path": "data/processed/localites_rgph5_placees.csv"},
                          {"path": "outputs/exposition_evenements/resume.json"}]}},
    {"id": "34", "num": 34, "label": "Communes reconstruites (contours approximatifs)",
     "script": "34_communes_reconstruites.py", "category": "Exposition",
     "outputs": ["data/processed/communes_reconstruites_ansd.geojson"],
     "exports": {"data": [{"path": "outputs/exposition_evenements/communes_reconstruites_resume.json"}]}},
    {"id": "35", "num": 35, "label": "Telechargement des donnees de l'ANSD (API SDMX)",
     "script": "35_telecharger_odp_ansd.py", "category": "Donnees ANSD",
     "outputs": ["data/raw/ansd/odp/MANIFEST.json"],
     "exports": {"data": [{"path": "data/raw/ansd/odp/DF_TX_PAUV.csv"},
                          {"path": "data/raw/ansd/odp/DF_PROJ_POP_2050_DEP.csv"}]}},
    {"id": "36", "num": 36, "label": "Correspondance des codes de zone ANSD / ClimatSen",
     "script": "36_correspondance_zones_ansd.py", "category": "Donnees ANSD",
     "outputs": ["data/processed/correspondance_zones_ansd.csv"], "exports": {}},
    {"id": "37", "num": 37, "label": "Exposition projetee 2026 et 2030",
     "script": "37_exposition_projetee.py", "category": "Exposition",
     "outputs": ["outputs/exposition_evenements/population_touchee_projetee.csv"],
     "exports": {"data": [{"path": "outputs/exposition_evenements/population_projetee_zones.csv"}]}},
]

SYNCHRO_ANSD = "data/raw/ansd/odp/.synchro.json"
MANIFESTE_ANSD = "data/raw/ansd/odp/MANIFEST.json"

# Un meme lancement ecrit les sorties de plusieurs etapes a quelques secondes
# d'intervalle: sans marge, une etape executee dans la meme seconde que son
# amont passait pour perimee (constate sur 01 et 03, ecrits a 01:33:48).
MARGE_SECONDES = 120

# Au-dela, les sorties d'une meme etape ne viennent pas du meme lancement: un
# rapport ou une table peut decrire un etat anterieur (constate sur l'etape
# 11, dont le rapport date de mars et les caracteristiques d'aout).
ECART_HETEROGENE_JOURS = 1.0

DESCRIPTION = (
    "Etat de la chaine de traitement de la plateforme (module Pipeline): pour "
    "chaque etape (detection des extremes, export, extraction des indices "
    "SST, teleconnexions, K-Means, cartes, veille, indice de risque, habitants "
    "touches, communes, donnees de l'ANSD), quels fichiers de sortie "
    "existent, de quand ils datent, et si une etape est a relancer parce que "
    "ses sorties sont plus anciennes que celles dont elle depend. A utiliser "
    "pour 'les resultats sont-ils a jour', 'quand l'analyse a-t-elle tourne "
    "pour la derniere fois', ou avant d'interpreter un resultat qui pourrait "
    "etre perime. Donne aussi la derniere synchronisation avec l'API SDMX de "
    "l'ANSD (onglet Donnees ANSD : date, resultat, erreur)."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "step": {"type": "string",
                 "description": "Identifiant d'une etape (01, 02, 03, 03b, "
                                "sst, 04, 11, 14, 19-22 veille, 26 27 29 indice "
                                "de risque, 33 34 37 exposition, 35 36 ANSD). "
                                "Omettre pour toutes."},
    },
    "required": [],
}


def _mtime(chemin: Path):
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


def _date(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _chemins_attendus(etape):
    """Sorties principales, puis exports, sans doublon ni motif glob."""
    vus, chemins = set(), []
    for chemin in etape.get("outputs", []):
        if chemin not in vus:
            vus.add(chemin)
            chemins.append((chemin, True))
    for groupe in etape.get("exports", {}).values():
        for item in groupe:
            if item.get("fmt") == "zip_glob":
                continue  # dossier entier, pas un fichier attendu
            if item["path"] not in vus:
                vus.add(item["path"])
                chemins.append((item["path"], False))
    return chemins


def _examiner(etape, base: Path):
    presents, manquants, dates = 0, [], []
    principale_la_plus_recente = None
    for chemin, principal in _chemins_attendus(etape):
        ts = _mtime(base / chemin)
        if ts is None:
            manquants.append(chemin)
            continue
        presents += 1
        dates.append(ts)
        if principal and (principale_la_plus_recente is None
                          or ts > principale_la_plus_recente):
            principale_la_plus_recente = ts
    return {
        "attendus": presents + len(manquants),
        "presents": presents,
        "manquants": manquants,
        "plus_recent": max(dates) if dates else None,
        "plus_ancien": min(dates) if dates else None,
        "principale": principale_la_plus_recente,
    }


def _lire_json(chemin: Path):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _synchro_ansd(base: Path):
    """Ce que montre l'onglet Donnees ANSD : derniere synchronisation (script
    38) et date de la copie des jeux de l'ANSD (manifeste du script 35)."""
    etat = _lire_json(base / SYNCHRO_ANSD)
    manifeste = _lire_json(base / MANIFESTE_ANSD) or {}
    fichiers = manifeste.get("fichiers") or []
    dates = sorted(f.get("telecharge_le") for f in fichiers if f.get("telecharge_le"))
    sortie = {
        "jeux": [f.get("fichier") for f in fichiers],
        "copie_telechargee_le": dates[-1] if dates else None,
        "source": manifeste.get("source"),
    }
    if not etat:
        sortie["derniere_synchronisation"] = None
        sortie["note"] = ("aucune synchronisation enregistree sur ce serveur (bouton "
                          "Synchroniser de l'onglet Donnees ANSD, administrateur)")
        return sortie
    sortie["derniere_synchronisation"] = {
        cle: etat.get(cle) for cle in ("etat", "resultat", "debut", "fin", "derniere_verification",
                                       "derniere_mise_a_jour",
                                       "fichiers_modifies", "erreur") if etat.get(cle)}
    return sortie


def _courte(ligne):
    return {cle: ligne[cle] for cle in ("etape", "libelle", "statut", "derniere_execution")}


def run(params, data):
    etapes = list(data["pipeline"]["steps"])
    connus = {e["id"] for e in etapes}
    complementaires = data["pipeline"].get("complementaires", ETAPES_COMPLEMENTAIRES)
    etapes += [e for e in complementaires if e["id"] not in connus]
    base = Path(data["pipeline"]["base"])
    examens = {e["id"]: _examiner(e, base) for e in etapes}

    demande = params.get("step")
    if demande is not None:
        demande = str(demande).strip().lower()
        ids = {e["id"].lower(): e["id"] for e in etapes}
        if demande not in ids:
            raise ToolInputError("Etape inconnue: %r. Valeurs acceptees: %s."
                                 % (params.get("step"),
                                    ", ".join(e["id"] for e in etapes)))
        demande = ids[demande]

    lignes = []
    for etape in etapes:
        if demande is not None and etape["id"] != demande:
            continue
        ex = examens[etape["id"]]
        # Perime si la plus ANCIENNE de nos sorties precede la sortie
        # principale la plus recente d'une etape amont.
        amont_plus_recent = []
        for dep in DEPENDANCES.get(etape["id"], []):
            amont = examens.get(dep, {}).get("principale")
            if amont is not None and ex["plus_ancien"] is not None \
                    and ex["plus_ancien"] < amont - MARGE_SECONDES:
                amont_plus_recent.append(dep)

        ecart_jours = None
        if ex["plus_recent"] is not None:
            ecart_jours = (ex["plus_recent"] - ex["plus_ancien"]) / 86400.0

        if ex["presents"] == 0:
            statut = "jamais execute (aucune sortie)"
        elif amont_plus_recent:
            statut = "a relancer"
        elif ex["manquants"]:
            statut = "incomplet"
        else:
            statut = "a jour"

        lignes.append({
            "etape": etape["id"],
            "ordre": etape.get("num"),
            "libelle": etape["label"],
            "script": etape["script"],
            "categorie": etape.get("category"),
            "statut": statut,
            "fichiers_presents": "%d/%d" % (ex["presents"], ex["attendus"]),
            "derniere_execution": _date(ex["plus_recent"]),
            "plus_ancienne_sortie": _date(ex["plus_ancien"]),
            "sorties_de_lancements_differents": (
                ecart_jours is not None and ecart_jours > ECART_HETEROGENE_JOURS),
            "ecart_entre_sorties_jours": (round(ecart_jours, 1)
                                          if ecart_jours is not None else None),
            "depend_de": DEPENDANCES.get(etape["id"], []),
            "amont_plus_recent_que_cette_etape": amont_plus_recent,
            "fichiers_manquants": ex["manquants"][:6],
        })

    if demande is None:
        # Vue d'ensemble : 20 etapes detaillees depassent le plafond d'un
        # resultat d'outil, et la reduction couperait la FIN de la liste (les
        # etapes recentes). Une etape a jour et homogene tient en une ligne ;
        # son detail s'obtient avec step=<id>.
        lignes = [_courte(l) if l["statut"] == "a jour"
                  and not l["sorties_de_lancements_differents"] else l for l in lignes]

    resume = {}
    for ligne in lignes:
        resume[ligne["statut"]] = resume.get(ligne["statut"], 0) + 1
    sortie = {
        "n_etapes": len(lignes),
        "resume": resume,
        "etapes": lignes,
        "lecture": ("'a relancer' = au moins une sortie de l'etape est plus "
                    "ancienne que la sortie principale d'une etape dont elle "
                    "depend: ses resultats peuvent decrire des donnees qui "
                    "ont change depuis. sorties_de_lancements_differents = "
                    "les fichiers d'une meme etape ont plus d'un jour "
                    "d'ecart: certains decrivent peut-etre un etat anterieur. "
                    "Detail d'une etape a jour (fichiers, dependances) : step=<id>."),
        "source": ("Module Pipeline du dashboard (scripts/vues/pipeline.py), plus les "
                   "etapes 26-37 (indice de risque, exposition, ANSD)"),
    }
    if demande is None or demande in ("35", "36", "37"):
        sortie["synchronisation_ansd"] = _synchro_ansd(base)
    return sortie
