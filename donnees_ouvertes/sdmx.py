"""Messages SDMX (norme ISO 17369) : structure en SDMX-JSON 2.0, donnees en
SDMX-CSV 2.0 et SDMX-JSON 2.0.

Une seule structure de donnees (DSD) sert les cinq flux, parce qu'ils ont la
meme forme : une valeur par (frequence, zone, indicateur, periode).

    FREQ        A (annuel) ou D (journalier)            liste CL_FREQ
    REF_AREA    pays, region, departement, arrondissement, commune
                (P-codes OCHA ; communes : P-code du departement + nom ANSD)
                                                         liste CL_ZONE
    INDICATOR   POPULATION, INDICE_RISQUE, POPULATION_TOUCHEE...
                                                         liste CL_INDICATEUR
    TIME_PERIOD 2023, 2012-09-28...
    OBS_VALUE   la valeur
    UNIT_MEASURE attribut d'observation                  liste CL_UNITE

Les identifiants de concepts (FREQ, REF_AREA, TIME_PERIOD, OBS_VALUE,
UNIT_MEASURE) sont ceux des concepts transversaux de la norme : un outil SDMX
les reconnait sans configuration. Les libelles sont en francais.

Agence de maintenance : CLIMATSEN. Ces structures sont celles de ClimatSen,
pas des structures officielles de l'ANSD.
"""
import csv
import io
import uuid
from datetime import datetime, timezone

import pandas as pd

from . import sources

AGENCE = "CLIMATSEN"
VERSION = "1.0"
DSD = "DSD_CLIMATSEN"
SCHEMA_DONNEES = ("https://raw.githubusercontent.com/sdmx-twg/sdmx-json/v2.0.0/"
                  "data-message/tools/schemas/2.0.0/sdmx-json-data-schema.json")
SCHEMA_STRUCTURE = ("https://raw.githubusercontent.com/sdmx-twg/sdmx-json/v2.0.0/"
                    "structure-message/tools/schemas/2.0.0/sdmx-json-structure-schema.json")

TYPE_CSV = "application/vnd.sdmx.data+csv; version=2.0.0; charset=utf-8"
TYPE_JSON_DONNEES = "application/vnd.sdmx.data+json; version=2.0.0; charset=utf-8"
TYPE_JSON_STRUCTURE = "application/vnd.sdmx.structure+json; version=2.0.0; charset=utf-8"

DIMENSIONS = ("FREQ", "REF_AREA", "INDICATOR")
FREQUENCES = {"A": "Annuelle", "D": "Journalière"}
CONCEPTS = {
    "FREQ": "Fréquence",
    "REF_AREA": "Zone de référence",
    "INDICATOR": "Indicateur",
    "TIME_PERIOD": "Période",
    "OBS_VALUE": "Valeur observée",
    "UNIT_MEASURE": "Unité de mesure",
}


def _urn(classe, ident, sous=None):
    paquet = {"Codelist": "codelist", "ConceptScheme": "conceptscheme",
              "Concept": "conceptscheme", "DataStructure": "datastructure",
              "Dataflow": "datastructure"}[classe]
    base = "urn:sdmx:org.sdmx.infomodel.%s.%s=%s:%s(%s)" % (paquet, classe, AGENCE, ident, VERSION)
    return base + ("." + sous if sous else "")


def _concept(ident):
    return _urn("Concept", "CS_CLIMATSEN", ident)


def ref_flux(jeu):
    return "%s:%s(%s)" % (AGENCE, jeu.flux, VERSION)


def maintenant():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- observations ------------------------------------------------------------

def observations(jeu, cle=None, debut=None, fin=None) -> pd.DataFrame:
    """Table longue d'un jeu : FREQ, REF_AREA, INDICATOR, TIME_PERIOD,
    OBS_VALUE, UNIT_MEASURE. Les valeurs manquantes ne sont pas emises."""
    t = sources.table(jeu.id)
    longue = t.melt(id_vars=["code", "periode"], value_vars=list(jeu.indicateurs),
                    var_name="INDICATOR", value_name="OBS_VALUE")
    longue = longue.dropna(subset=["OBS_VALUE"])
    longue.insert(0, "FREQ", jeu.freq)
    longue = longue.rename(columns={"code": "REF_AREA", "periode": "TIME_PERIOD"})
    longue["UNIT_MEASURE"] = longue["INDICATOR"].map(lambda c: sources.INDICATEURS[c][1])

    if cle:
        for dim, valeurs in zip(DIMENSIONS, cle):
            if valeurs:
                longue = longue[longue[dim].isin(valeurs)]
    # TIME_PERIOD est une chaine ISO 8601 (AAAA ou AAAA-MM-JJ) : l'ordre
    # lexicographique suffit. Une borne de fin courte ("2012") doit inclure
    # tous les jours de 2012 : on la complete par "~", qui se classe apres
    # les chiffres et le tiret.
    if debut:
        longue = longue[longue["TIME_PERIOD"] >= debut]
    if fin:
        longue = longue[longue["TIME_PERIOD"] <= (fin if len(fin) >= 10 else fin + "~")]
    ordre = {c: i for i, c in enumerate(jeu.indicateurs)}
    longue = longue.assign(_o=longue["INDICATOR"].map(ordre))
    longue = longue.sort_values(["REF_AREA", "_o", "TIME_PERIOD"]).drop(columns="_o")
    return longue.reset_index(drop=True)


def lire_cle(cle: str):
    """Cle de requete SDMX REST : 'A.SN0101+SN0102.POPULATION'.
    Une position vide ou '*' vaut 'toutes les valeurs'."""
    if cle in (None, "", "all", "*"):
        return None
    morceaux = cle.split(".")
    if len(morceaux) != len(DIMENSIONS):
        raise ValueError("La clé doit avoir %d positions séparées par des points "
                         "(%s), par exemple A.SN0101.POPULATION ; reçu : %r"
                         % (len(DIMENSIONS), ".".join(DIMENSIONS), cle))
    return [set() if m in ("", "*") else set(m.split("+")) for m in morceaux]


# --- SDMX-CSV 2.0 -------------------------------------------------------------

def csv_donnees(jeu, obs: pd.DataFrame, libelles: bool = False) -> str:
    """SDMX-CSV 2.0 : colonnes STRUCTURE, STRUCTURE_ID, ACTION, puis
    dimensions, mesure et attributs. Avec libelles=True, chaque code est suivi
    de son libelle ('A: Annuelle'), comme le prevoit le parametre labels=both."""
    noms = _libelles_codes(obs) if libelles else None
    tampon = io.StringIO()
    w = csv.writer(tampon, lineterminator="\n")
    colonnes = list(DIMENSIONS) + ["TIME_PERIOD", "OBS_VALUE", "UNIT_MEASURE"]
    entete = ["STRUCTURE", "STRUCTURE_ID", "ACTION"]
    entete += ["%s: %s" % (c, CONCEPTS[c]) for c in colonnes] if libelles else colonnes
    w.writerow(entete)
    ref = ref_flux(jeu)
    for ligne in obs[colonnes].itertuples(index=False):
        valeurs = []
        for col, v in zip(colonnes, ligne):
            v = sources.valeur_json(v)
            if noms and col in noms and v in noms[col]:
                v = "%s: %s" % (v, noms[col][v])
            valeurs.append(v)
        w.writerow(["dataflow", ref, "I"] + valeurs)
    return tampon.getvalue()


def _libelles_codes(obs):
    zones = {z["id"]: z["nom"] for z in sources.zones()}
    return {"FREQ": FREQUENCES, "REF_AREA": zones,
            "INDICATOR": {c: l for c, (l, _) in sources.INDICATEURS.items()},
            "UNIT_MEASURE": sources.UNITES}


# --- SDMX-JSON 2.0, donnees --------------------------------------------------

def json_donnees(jeu, obs: pd.DataFrame) -> dict:
    """Message de donnees SDMX-JSON 2.0, toutes les dimensions au niveau de
    l'observation (cle d'observation 'i:j:k:l')."""
    zones = {z["id"]: z for z in sources.zones()}
    dims, index = [], {}
    for pos, dim in enumerate(DIMENSIONS + ("TIME_PERIOD",)):
        valeurs = list(dict.fromkeys(obs[dim])) if len(obs) else []
        index[dim] = {v: i for i, v in enumerate(valeurs)}
        if dim == "FREQ":
            vals = [{"id": v, "name": FREQUENCES[v]} for v in valeurs]
        elif dim == "REF_AREA":
            vals = []
            for v in valeurs:
                z = {"id": v, "name": zones.get(v, {}).get("nom", v)}
                if zones.get(v, {}).get("parent"):
                    z["parent"] = zones[v]["parent"]
                vals.append(z)
        elif dim == "INDICATOR":
            vals = [{"id": v, "name": sources.INDICATEURS[v][0]} for v in valeurs]
        else:
            vals = [{"value": v} for v in valeurs]
        d = {"id": dim, "name": CONCEPTS[dim], "keyPosition": pos, "values": vals or [{"value": ""}]}
        if dim in ("FREQ", "REF_AREA", "TIME_PERIOD"):
            d["roles"] = [dim]
        dims.append(d)

    unites = list(dict.fromkeys(obs["UNIT_MEASURE"])) if len(obs) else []
    i_unite = {u: i for i, u in enumerate(unites)}
    observations_ = {}
    for r in obs.itertuples(index=False):
        k = ":".join(str(index[d][getattr(r, d)]) for d in DIMENSIONS + ("TIME_PERIOD",))
        observations_[k] = [sources.valeur_json(r.OBS_VALUE), i_unite[r.UNIT_MEASURE]]

    structure = {
        "links": [{"rel": "dataflow", "urn": _urn("Dataflow", jeu.flux)},
                  {"rel": "datastructure", "urn": _urn("DataStructure", DSD)}],
        "name": jeu.titre, "names": {"fr": jeu.titre},
        "dataSets": [0],
        "dimensions": {"dataSet": [], "series": [], "observation": dims},
        "measures": {"observation": [{"id": "OBS_VALUE", "name": CONCEPTS["OBS_VALUE"],
                                      "roles": ["OBS_VALUE"]}]},
        "attributes": {"dataSet": [], "series": [], "observation": [{
            "id": "UNIT_MEASURE", "name": CONCEPTS["UNIT_MEASURE"], "roles": ["UNIT_MEASURE"],
            "relationship": {"observation": {}},
            "values": [{"id": u, "name": sources.UNITES[u]} for u in unites] or [None]}]},
    }
    return {
        "meta": _meta("Données " + jeu.flux, SCHEMA_DONNEES),
        "data": {"structures": [structure],
                 "dataSets": [{"structure": 0, "action": "Information",
                               "links": [{"rel": "dataflow", "urn": _urn("Dataflow", jeu.flux)}],
                               "observations": observations_}]},
    }


def _meta(nom, schema):
    return {"schema": schema, "id": "IREF" + uuid.uuid4().hex[:12].upper(), "test": False,
            "prepared": maintenant(), "contentLanguages": ["fr"],
            "name": nom, "names": {"fr": nom},
            "sender": {"id": AGENCE, "name": "ClimatSen", "names": {"fr": "ClimatSen"}}}


# --- SDMX-JSON 2.0, structure -------------------------------------------------

def _maintenable(ident, nom, description=None):
    m = {"id": ident, "agencyID": AGENCE, "version": VERSION,
         "name": nom, "names": {"fr": nom}}
    if description:
        m["description"] = description
        m["descriptions"] = {"fr": description}
    return m


def _code(ident, nom, parent=None, annotations=None):
    c = {"id": ident, "name": nom, "names": {"fr": nom}}
    if parent:
        c["parent"] = parent
    if annotations:
        c["annotations"] = annotations
    return c


def codelists(ids=None) -> list:
    listes = []
    if ids is None or "CL_FREQ" in ids:
        cl = _maintenable("CL_FREQ", "Fréquence")
        cl["codes"] = [_code(k, v) for k, v in FREQUENCES.items()]
        listes.append(cl)
    if ids is None or "CL_ZONE" in ids:
        cl = _maintenable("CL_ZONE", "Zones géographiques du Sénégal",
                          "Pays, régions, départements et arrondissements identifiés par leur "
                          "P-code OCHA (COD-AB 2024) ; communes identifiées par le P-code du "
                          "département suivi du nom ANSD. Annotation CODE_ANSD_SDMX : le code de "
                          "la même zone dans la liste CL_REF_AREA de l'ANSD (agence SN1), pour "
                          "joindre ces données à celles de l'Open Data Platform de l'ANSD.")
        codes = []
        for z in sources.zones():
            ann = [{"type": "NIVEAU", "title": z["niveau"]}]
            if "code_ansd" in z:
                ann.append({"type": "CODE_ANSD", "title": str(z["code_ansd"])})
            if "code_ansd_sdmx" in z:
                # Code de la meme zone dans la liste CL_REF_AREA de l'ANSD (agence SN1).
                ann.append({"type": "CODE_ANSD_SDMX", "title": z["code_ansd_sdmx"]})
            codes.append(_code(z["id"], z["nom"], z["parent"], ann))
        cl["codes"] = codes
        listes.append(cl)
    if ids is None or "CL_INDICATEUR" in ids:
        cl = _maintenable("CL_INDICATEUR", "Indicateurs de ClimatSen")
        cl["codes"] = [_code(k, l, annotations=[{"type": "UNITE", "title": u}])
                       for k, (l, u) in sources.INDICATEURS.items()]
        listes.append(cl)
    if ids is None or "CL_UNITE" in ids:
        cl = _maintenable("CL_UNITE", "Unités de mesure")
        cl["codes"] = [_code(k, v) for k, v in sources.UNITES.items()]
        listes.append(cl)
    return listes


def _schema_concepts():
    cs = _maintenable("CS_CLIMATSEN", "Concepts de ClimatSen")
    cs["concepts"] = [{"id": k, "name": v, "names": {"fr": v}} for k, v in CONCEPTS.items()]
    return cs


def _dsd():
    enum = {"FREQ": "CL_FREQ", "REF_AREA": "CL_ZONE", "INDICATOR": "CL_INDICATEUR"}
    d = _maintenable(DSD, "Statistiques de ClimatSen",
                     "Une valeur par fréquence, zone, indicateur et période.")
    d["dataStructureComponents"] = {
        "dimensionList": {
            "id": "DimensionDescriptor",
            "dimensions": [{"id": dim, "position": i, "conceptIdentity": _concept(dim),
                            "localRepresentation": {"enumeration": _urn("Codelist", enum[dim])}}
                           for i, dim in enumerate(DIMENSIONS)],
            "timeDimension": {"id": "TIME_PERIOD", "conceptIdentity": _concept("TIME_PERIOD"),
                              "localRepresentation": {"format": {"dataType": "ObservationalTimePeriod"}}},
        },
        "attributeList": {
            "id": "AttributeDescriptor",
            "attributes": [{"id": "UNIT_MEASURE", "usage": "mandatory",
                            "attributeRelationship": {"observation": {}},
                            "conceptIdentity": _concept("UNIT_MEASURE"),
                            "localRepresentation": {"enumeration": _urn("Codelist", "CL_UNITE")}}],
        },
        "measureList": {
            "id": "MeasureDescriptor",
            "measures": [{"id": "OBS_VALUE", "conceptIdentity": _concept("OBS_VALUE"),
                          "localRepresentation": {"format": {"dataType": "Double"}}}],
        },
    }
    return d


def _flux(jeu):
    f = _maintenable(jeu.flux, jeu.titre, jeu.description)
    f["structure"] = _urn("DataStructure", DSD)
    ann = [{"type": "SOURCES", "title": "; ".join(sources.SOURCES[s]["nom"] for s in jeu.sources)},
           {"type": "LICENCE", "title": sources.LICENCE["nom"], "links": [
               {"rel": "licence", "href": sources.LICENCE["url"]}]},
           {"type": "PROGRAMME", "title": jeu.script}]
    if jeu.avertissement:
        ann.append({"type": "AVERTISSEMENT", "title": "Avertissement",
                    "text": jeu.avertissement, "texts": {"fr": jeu.avertissement}})
    f["annotations"] = ann
    return f


def json_structure(quoi="tout", ident=None) -> dict:
    """Message de structure SDMX-JSON 2.0. quoi : tout, dataflow,
    datastructure, codelist, conceptscheme."""
    jeux = [j for j in sources.JEUX.values() if sources.disponible(j)]
    data = {}
    if quoi in ("tout", "dataflow"):
        data["dataflows"] = [_flux(j) for j in jeux if ident in (None, "all", j.flux)]
    if quoi in ("tout", "datastructure"):
        data["dataStructures"] = [_dsd()] if ident in (None, "all", DSD) else []
    if quoi in ("tout", "codelist"):
        data["codelists"] = codelists(None if ident in (None, "all") else {ident})
    if quoi in ("tout", "conceptscheme"):
        data["conceptSchemes"] = [_schema_concepts()] if ident in (None, "all", "CS_CLIMATSEN") else []
    data = {k: v for k, v in data.items() if v}
    return {"meta": _meta("Structures de ClimatSen", SCHEMA_STRUCTURE), "data": data}
