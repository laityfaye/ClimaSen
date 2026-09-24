"""Outil get_pipeline_status: etat de la chaine de traitement (Phase 7).

Meme liste d'etapes que le module "Pipeline" du dashboard
(scripts/pages/pipeline.py, PIPELINE_STEPS): une seule source de verite, une
etape ajoutee au dashboard apparait ici sans rien toucher.

Pour chaque etape: ses sorties existent-elles, de quand datent-elles, et
surtout sont-elles PLUS ANCIENNES que celles des etapes dont elle depend ? Une
figure de teleconnexions produite avant la derniere detection des evenements
decrit un catalogue qui n'existe plus: c'est l'incoherence la plus facile a
commettre et la plus difficile a voir a l'oeil.

Ne renvoie que des chemins RELATIFS au projet et des dates: rien sur
l'organisation du serveur.
"""
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
}

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
    "SST, teleconnexions, K-Means, cartes), quels fichiers de sortie "
    "existent, de quand ils datent, et si une etape est a relancer parce que "
    "ses sorties sont plus anciennes que celles dont elle depend. A utiliser "
    "pour 'les resultats sont-ils a jour', 'quand l'analyse a-t-elle tourne "
    "pour la derniere fois', ou avant d'interpreter un resultat qui pourrait "
    "etre perime."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "step": {"type": "string",
                 "description": "Identifiant d'une etape (01, 02, 03, 03b, "
                                "sst, 04, 11, 14). Omettre pour toutes."},
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


def run(params, data):
    etapes = data["pipeline"]["steps"]
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

    resume = {}
    for ligne in lignes:
        resume[ligne["statut"]] = resume.get(ligne["statut"], 0) + 1
    return {
        "n_etapes": len(lignes),
        "resume": resume,
        "etapes": lignes,
        "lecture": ("'a relancer' = au moins une sortie de l'etape est plus "
                    "ancienne que la sortie principale d'une etape dont elle "
                    "depend: ses resultats peuvent decrire des donnees qui "
                    "ont change depuis. sorties_de_lancements_differents = "
                    "les fichiers d'une meme etape ont plus d'un jour "
                    "d'ecart: certains decrivent peut-etre un etat anterieur."),
        "source": "Module Pipeline du dashboard (scripts/pages/pipeline.py)",
    }
