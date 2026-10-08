"""Application FastAPI de l'API ouverte, montee sous /api/v1.

Lecture seule, sans compte ni cle : seules les donnees deja publiees sur la
plateforme sont servies. Le debit est borne par adresse (seau a jetons, comme
pour IRIS) et, en production, par nginx.
"""
from enum import Enum
from typing import Callable, Optional

from fastapi import FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from . import sdmx, sources

TYPE_CSV = "text/csv; charset=utf-8"
TYPE_GEOJSON = "application/geo+json"
LIMITE_MAX = 5000

DESCRIPTION = """
Les statistiques produites par **CLIMAT-SEN**, en lecture seule, sans compte ni clé.

* **`/donnees/{jeu}`** : un jeu de données en JSON (par défaut), CSV, SDMX-CSV ou
  SDMX-JSON, avec des filtres simples.
* **`/sdmx/...`** : la même chose au format SDMX (ISO 17369), avec les requêtes de
  l'API REST SDMX (`/sdmx/data/{flux}/{clé}`) et les structures (flux, structure de
  données, listes de codes) en SDMX-JSON 2.0.
* **`/geo/{niveau}.geojson`** : les contours avec leurs indicateurs, prêts pour QGIS.

Les zones sont identifiées par les **P-codes OCHA** ; les communes portent aussi leur
**code ANSD**. Sources : ANSD (RGPH-5 2023, EHCVM 2021-22, coordonnées des
localités), OCHA (COD-AB 2024), CHIRPS v2.0. Chaque réponse rappelle ses sources,
sa licence et ses limites.
"""


class NomJeu(str, Enum):
    departements = "departements"
    arrondissements = "arrondissements"
    communes = "communes"
    evenements = "evenements"
    annees = "annees"


class Format(str, Enum):
    json = "json"
    csv = "csv"
    sdmx_csv = "sdmx-csv"
    sdmx_json = "sdmx-json"


class Niveau(str, Enum):
    departements = "departements"
    arrondissements = "arrondissements"
    communes = "communes"


class TypeStructure(str, Enum):
    dataflow = "dataflow"
    datastructure = "datastructure"
    codelist = "codelist"
    conceptscheme = "conceptscheme"


class ErreurRequete(Exception):
    def __init__(self, message, statut=400, code="requete_invalide", entetes=None):
        self.message, self.statut, self.code = message, statut, code
        self.entetes = entetes or {}


def creer_api(ip_client: Optional[Callable[[Request], str]] = None,
              capacite: int = 120, recharge_par_seconde: float = 2.0) -> FastAPI:
    """ip_client : fonction qui donne l'adresse du client (celle d'IRIS, qui ne
    croit X-Forwarded-For que venant de nginx). Par defaut, l'adresse du pair."""
    from jarvis.ratelimit import TokenBucket

    ip_client = ip_client or (lambda r: r.client.host if r.client else "inconnu")
    seau = TokenBucket(capacity=capacite, refill_per_second=recharge_par_seconde)

    api = FastAPI(
        title="API ouverte CLIMAT-SEN",
        version="1.0",
        description=DESCRIPTION,
        docs_url="/docs", redoc_url=None, openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Catalogue", "description": "Ce que l'API publie."},
            {"name": "Données", "description": "Les jeux de données, en JSON, CSV ou SDMX."},
            {"name": "SDMX", "description": "API REST SDMX : données et structures."},
            {"name": "Contours", "description": "Contours GeoJSON avec indicateurs."},
        ],
    )
    api.state.seau = seau

    # La documentation interactive charge Swagger UI depuis jsDelivr : la CSP
    # du serveur (tout en 'self') la bloquerait. Elle est assouplie pour ces
    # deux pages seulement ; le reste de l'API ne renvoie pas de HTML.
    CSP_DOCS = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

    @api.middleware("http")
    async def _debit_et_entetes(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        autorise, attente = seau.consume(ip_client(request))
        if not autorise:
            reponse = _erreur(ErreurRequete(
                "Trop de requêtes : réessayez dans %d s." % attente, 429, "debit_depasse",
                {"Retry-After": str(attente)}))
        else:
            reponse = await call_next(request)
        # Donnees publiques, sans cookie ni session : n'importe quel site peut
        # les lire depuis le navigateur.
        reponse.headers["Access-Control-Allow-Origin"] = "*"
        reponse.headers.setdefault("Cache-Control", "public, max-age=900")
        if request.url.path.endswith("/docs"):
            reponse.headers["Content-Security-Policy"] = CSP_DOCS
        return reponse

    @api.exception_handler(ErreurRequete)
    async def _erreur_requete(request: Request, exc: ErreurRequete):
        return _erreur(exc)

    def base(request: Request) -> str:
        return str(request.base_url).rstrip("/") + request.scope.get("root_path", "")

    # --- catalogue ---------------------------------------------------------
    @api.get("/", tags=["Catalogue"], summary="Accueil de l'API")
    def accueil(request: Request):
        b = base(request)
        return {
            "nom": "API ouverte CLIMAT-SEN",
            "version": "1.0",
            "description": "Statistiques de CLIMAT-SEN sur les pluies extrêmes et la "
                           "population exposée au Sénégal, en lecture seule.",
            "documentation": b + "/docs",
            "catalogue": b + "/catalogue",
            "sdmx": {"flux": b + "/sdmx/dataflow", "structures": b + "/sdmx/structure"},
            "licence": sources.LICENCE,
        }

    @api.get("/catalogue", tags=["Catalogue"], summary="Jeux de données publiés")
    def catalogue(request: Request):
        b = base(request)
        return {"licence": sources.LICENCE,
                "jeux": [_fiche(j, b) for j in sources.JEUX.values() if sources.disponible(j)]}

    @api.get("/indicateurs", tags=["Catalogue"], summary="Indicateurs et unités")
    def indicateurs():
        jeux_par_ind = {}
        for j in sources.JEUX.values():
            for c in j.indicateurs:
                jeux_par_ind.setdefault(c, []).append(j.id)
        return [{"code": c, "colonne": c.lower(), "libelle": l, "unite": u,
                 "unite_libelle": sources.UNITES[u], "jeux": jeux_par_ind.get(c, [])}
                for c, (l, u) in sources.INDICATEURS.items()]

    @api.get("/zones", tags=["Catalogue"], summary="Zones géographiques et leurs codes")
    def zones(niveau: Optional[str] = Query(None, description="pays, region, departement, "
                                            "arrondissement ou commune"),
              parent: Optional[str] = Query(None, description="code de la zone parente, ex. SN0101"),
              format: Format = Format.json):
        z = sources.zones()
        if niveau:
            z = [x for x in z if x["niveau"] == niveau]
        if parent:
            z = [x for x in z if x["parent"] == parent]
        if format == Format.csv:
            import pandas as pd
            return _csv(pd.DataFrame(z, columns=["id", "nom", "niveau", "parent", "code_ansd"])
                        .astype({"code_ansd": "Int64"}), "zones")
        return z

    # --- donnees -----------------------------------------------------------
    @api.get("/donnees/{jeu}", tags=["Données"], summary="Un jeu de données, filtré")
    def donnees(
        request: Request,
        jeu: NomJeu,
        format: Format = Query(Format.json, description="json, csv, sdmx-csv ou sdmx-json"),
        code: Optional[str] = Query(None, description="codes de zones séparés par des virgules"),
        region: Optional[str] = Query(None, description="code (SN07) ou nom (Kolda) de la région"),
        departement: Optional[str] = Query(None, description="code (SN0703) ou nom du département ; "
                                           "pour les événements : département le plus touché"),
        indicateurs: Optional[str] = Query(None, description="codes d'indicateurs séparés par des "
                                           "virgules, ex. POPULATION,INDICE_RISQUE"),
        annee: Optional[int] = Query(None, ge=1981, le=2100, description="événements et années"),
        debut: Optional[str] = Query(None, description="date ou année de début (incluse)"),
        fin: Optional[str] = Query(None, description="date ou année de fin (incluse)"),
        phase: Optional[str] = Query(None, description="événements : Phase_1_debut, Phase_2_pleine, Phase_3_fin"),
        population_min: Optional[int] = Query(None, ge=0, description="événements : habitants touchés au moins"),
        tri: Optional[str] = Query(None, description="colonne de tri, ex. indice_risque, population_touchee"),
        ordre: str = Query("desc", pattern="^(asc|desc)$"),
        limite: int = Query(LIMITE_MAX, ge=1, le=LIMITE_MAX),
        decalage: int = Query(0, ge=0),
    ):
        j = _jeu(jeu.value)
        t = sources.table(j.id)
        t = _filtrer(t, j, code, region, departement, annee, debut, fin, phase, population_min)
        inds = _indicateurs(j, indicateurs)
        total = len(t)

        if format in (Format.sdmx_csv, Format.sdmx_json):
            obs = sdmx.observations(j, [set(), set(t["code"]), set(inds)])
            obs = obs[obs.set_index(["REF_AREA", "TIME_PERIOD"]).index.isin(
                t.set_index(["code", "periode"]).index)]
            return _sdmx(j, obs, format)

        if tri:
            col = tri.upper() if tri.upper() in j.indicateurs else tri
            if col not in t.columns:
                raise ErreurRequete("Tri impossible : colonne %r inconnue." % tri)
            t = t.sort_values(col, ascending=(ordre == "asc"), na_position="last")
        t = t.iloc[decalage: decalage + limite]
        descriptives = [c for c in t.columns if c not in sources.INDICATEURS]
        t = t[descriptives + inds]

        if format == Format.csv:
            return _csv(t.rename(columns={c: c.lower() for c in inds}), j.id)
        b = base(request)
        return {
            **_fiche(j, b, avec_liens=False),
            "unites": {c.lower(): sources.INDICATEURS[c][1] for c in inds},
            "total": total, "nombre": len(t), "decalage": decalage,
            "donnees": [sources.ligne_vers_dict(r) for _, r in t.iterrows()],
        }

    @api.get("/evenements/{date}", tags=["Données"], summary="Un événement de pluie extrême")
    def evenement(date: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2012-09-28"])):
        j = _jeu("evenements")
        t = sources.table("evenements")
        ligne = t[t["periode"] == date]
        if ligne.empty:
            raise ErreurRequete("Aucun événement de pluie extrême détecté le %s." % date,
                                404, "introuvable")
        rang = int((t["POPULATION_TOUCHEE"] > ligne["POPULATION_TOUCHEE"].iloc[0]).sum()) + 1
        return {**sources.ligne_vers_dict(ligne.iloc[0]),
                "rang_population_touchee": rang, "evenements": len(t),
                "unites": {c.lower(): sources.INDICATEURS[c][1] for c in j.indicateurs},
                "avertissement": j.avertissement,
                "sources": [sources.SOURCES[s] for s in j.sources],
                "licence": sources.LICENCE}

    # --- contours ----------------------------------------------------------
    @api.get("/geo/{niveau}.geojson", tags=["Contours"],
             summary="Contours d'un niveau, avec ses indicateurs")
    def geo(niveau: Niveau):
        j = _jeu(niveau.value)
        if not sources.CONTOURS[niveau.value].exists():
            raise ErreurRequete("Contours indisponibles.", 503, "indisponible")
        import json
        g = dict(sources.geojson(niveau.value))
        g["metadata"] = {"titre": j.titre, "licence": sources.LICENCE,
                         "sources": [sources.SOURCES[s] for s in j.sources],
                         "avertissement": j.avertissement}
        return Response(json.dumps(g, ensure_ascii=False), media_type=TYPE_GEOJSON)

    # --- SDMX --------------------------------------------------------------
    FLUX = Path(..., description="DF_RISQUE_DEPARTEMENTS ou CLIMATSEN,DF_RISQUE_DEPARTEMENTS,1.0")
    DEBUT = Query(None, description="début, ex. 2005 ou 2005-07-01")
    FIN = Query(None, description="fin, ex. 2012 ou 2012-09-30")
    FORMAT = Query(None, description="sdmx-csv ou sdmx-json ; à défaut, l'en-tête Accept, puis SDMX-JSON")
    LABELS = Query("id", pattern="^(id|both)$", description="SDMX-CSV : both ajoute les libellés")

    @api.get("/sdmx/data/{flux}", tags=["SDMX"], summary="Données SDMX d'un flux")
    def sdmx_donnees(request: Request, flux: str = FLUX,
                     startPeriod: Optional[str] = DEBUT, endPeriod: Optional[str] = FIN,
                     format: Optional[Format] = FORMAT, labels: str = LABELS):
        return _donnees_sdmx(request, flux, "all", startPeriod, endPeriod, format, labels)

    @api.get("/sdmx/data/{flux}/{cle}", tags=["SDMX"],
             summary="Données SDMX d'un flux, filtrées par clé")
    def sdmx_donnees_cle(
        request: Request, flux: str = FLUX,
        cle: str = Path(..., description="FREQ.REF_AREA.INDICATOR, ex. A.SN0703+SN1204.INDICE_RISQUE ; "
                                         "position vide = toutes les valeurs"),
        startPeriod: Optional[str] = DEBUT, endPeriod: Optional[str] = FIN,
        format: Optional[Format] = FORMAT, labels: str = LABELS):
        return _donnees_sdmx(request, flux, cle, startPeriod, endPeriod, format, labels)

    def _donnees_sdmx(request, flux, cle, startPeriod, endPeriod, format, labels):
        j = _jeu_par_flux(flux)
        try:
            c = sdmx.lire_cle(cle)
        except ValueError as e:
            raise ErreurRequete(str(e))
        for p in (startPeriod, endPeriod):
            _verifier_periode(p)
        obs = sdmx.observations(j, c, startPeriod, endPeriod)
        if obs.empty:
            raise ErreurRequete("Aucune observation ne correspond à la requête.", 404, "NoResultsFound")
        if format is None:
            accept = request.headers.get("accept", "")
            format = Format.sdmx_csv if "csv" in accept else Format.sdmx_json
        elif format in (Format.json, Format.csv):
            format = Format.sdmx_json if format == Format.json else Format.sdmx_csv
        return _sdmx(j, obs, format, labels == "both")

    @api.get("/sdmx/structure", tags=["SDMX"], summary="Toutes les structures (SDMX-JSON 2.0)")
    def sdmx_structures():
        return _json_sdmx(sdmx.json_structure())

    @api.get("/sdmx/{type_}", tags=["SDMX"], summary="Structures d'un type (SDMX-JSON 2.0)")
    def sdmx_type(type_: TypeStructure):
        return _structure(type_, "all", "all", "latest")

    @api.get("/sdmx/{type_}/{agence}/{ident}", tags=["SDMX"], include_in_schema=False)
    def sdmx_structure_id(type_: TypeStructure, agence: str, ident: str):
        return _structure(type_, agence, ident, "latest")

    @api.get("/sdmx/{type_}/{agence}/{ident}/{version}", tags=["SDMX"],
             summary="Une structure (SDMX-JSON 2.0)")
    def sdmx_structure(type_: TypeStructure, agence: str, ident: str, version: str):
        return _structure(type_, agence, ident, version)

    def _structure(type_, agence, ident, version):
        if agence not in ("all", "*", sdmx.AGENCE):
            raise ErreurRequete("Agence inconnue : %s (seule %s est servie)." % (agence, sdmx.AGENCE),
                                404, "NoResultsFound")
        if version not in ("latest", "all", "*", "~", "+", sdmx.VERSION):
            raise ErreurRequete("Version inconnue : %s." % version, 404, "NoResultsFound")
        msg = sdmx.json_structure(type_.value, None if ident in ("all", "*") else ident)
        if not msg["data"]:
            raise ErreurRequete("Structure introuvable : %s." % ident, 404, "NoResultsFound")
        return _json_sdmx(msg)

    return api


# --- outils -------------------------------------------------------------------

def _erreur(exc: ErreurRequete):
    return JSONResponse({"erreur": {"code": exc.code, "message": exc.message}},
                        status_code=exc.statut, headers=exc.entetes)


def _jeu(ident):
    j = sources.JEUX[ident]
    if not sources.disponible(j):
        raise ErreurRequete("Jeu de données momentanément indisponible.", 503, "indisponible")
    return j


def _jeu_par_flux(flux):
    morceaux = flux.split(",")
    if len(morceaux) == 3:
        agence, ident, version = morceaux
        if agence not in (sdmx.AGENCE, "all", "*") or version not in (sdmx.VERSION, "latest", "*", "~"):
            raise ErreurRequete("Flux inconnu : %s." % flux, 404, "NoResultsFound")
    elif len(morceaux) == 1:
        ident = flux
    else:
        raise ErreurRequete("Flux mal formé : %s (attendu ID ou AGENCE,ID,VERSION)." % flux)
    for j in sources.JEUX.values():
        if j.flux == ident or j.id == ident:
            return _jeu(j.id)
    raise ErreurRequete("Flux inconnu : %s. Voir /sdmx/dataflow." % ident, 404, "NoResultsFound")


def _verifier_periode(p):
    import re
    if p and not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", p):
        raise ErreurRequete("Période mal formée : %r (attendu AAAA, AAAA-MM ou AAAA-MM-JJ)." % p)


def _indicateurs(j, demandes):
    if not demandes:
        return list(j.indicateurs)
    codes = [c.strip().upper() for c in demandes.split(",") if c.strip()]
    inconnus = [c for c in codes if c not in j.indicateurs]
    if inconnus:
        raise ErreurRequete("Indicateur(s) absent(s) du jeu %s : %s. Disponibles : %s."
                            % (j.id, ", ".join(inconnus), ", ".join(j.indicateurs)))
    return codes


def _filtrer(t, j, code, region, departement, annee, debut, fin, phase, population_min):
    from .sources import cle
    if code:
        codes = {c.strip() for c in code.split(",") if c.strip()}
        t = t[t["code"].isin(codes)]
    if region:
        if "code_region" not in t.columns:
            raise ErreurRequete("Le filtre region ne s'applique pas au jeu %s." % j.id)
        t = t[(t["code_region"] == region) | (t["region"].map(cle) == cle(region))]
    if departement:
        if j.id == "evenements":
            colc, coln = "code_departement_le_plus_touche", "departement_le_plus_touche"
        elif j.id == "departements":
            colc, coln = "code", "nom"
        elif "code_departement" in t.columns:
            colc, coln = "code_departement", "departement"
        else:
            raise ErreurRequete("Le filtre departement ne s'applique pas au jeu %s." % j.id)
        t = t[(t[colc] == departement) | (t[coln].map(lambda n: cle(n) if isinstance(n, str) else "")
                                          == cle(departement))]
    temporel = j.id in ("evenements", "annees")
    if (annee or debut or fin) and not temporel:
        raise ErreurRequete("Les filtres annee, debut et fin s'appliquent aux jeux evenements et annees.")
    for p in (debut, fin):
        _verifier_periode(p)
    if annee:
        t = t[t["periode"].str[:4] == str(annee)]
    if debut:
        t = t[t["periode"] >= debut]
    if fin:
        t = t[t["periode"] <= (fin if len(fin) >= 10 else fin + "~")]
    if phase or population_min is not None:
        if j.id != "evenements":
            raise ErreurRequete("Les filtres phase et population_min s'appliquent au jeu evenements.")
        if phase:
            t = t[t["phase"] == phase]
        if population_min is not None:
            t = t[t["POPULATION_TOUCHEE"] >= population_min]
    return t


def _fiche(j, b, avec_liens=True):
    f = {"jeu": j.id, "titre": j.titre, "description": j.description,
         "niveau": j.niveau, "frequence": sdmx.FREQUENCES[j.freq],
         "flux_sdmx": sdmx.ref_flux(j),
         "indicateurs": [{"code": c, "colonne": c.lower(), "libelle": sources.INDICATEURS[c][0],
                          "unite": sources.INDICATEURS[c][1]} for c in j.indicateurs],
         "sources": [sources.SOURCES[s] for s in j.sources],
         "programme": j.script, "licence": sources.LICENCE}
    if j.avertissement:
        f["avertissement"] = j.avertissement
    if avec_liens:
        f["liens"] = {
            "json": "%s/donnees/%s" % (b, j.id),
            "csv": "%s/donnees/%s?format=csv" % (b, j.id),
            "sdmx_csv": "%s/sdmx/data/%s?format=sdmx-csv" % (b, j.flux),
            "sdmx_json": "%s/sdmx/data/%s" % (b, j.flux),
        }
        if j.id in sources.CONTOURS:
            f["liens"]["geojson"] = "%s/geo/%s.geojson" % (b, j.id)
    return f


def _csv(df, nom):
    corps = df.to_csv(index=False, lineterminator="\n")
    return Response(corps, media_type=TYPE_CSV, headers={
        "Content-Disposition": 'inline; filename="climatsen_%s.csv"' % nom})


def _sdmx(j, obs, format, libelles=False):
    if format == Format.sdmx_csv:
        return Response(sdmx.csv_donnees(j, obs, libelles), media_type=sdmx.TYPE_CSV, headers={
            "Content-Disposition": 'inline; filename="%s.csv"' % j.flux})
    return _json_sdmx(sdmx.json_donnees(j, obs), sdmx.TYPE_JSON_DONNEES)


def _json_sdmx(msg, media=sdmx.TYPE_JSON_STRUCTURE):
    import json
    return Response(json.dumps(msg, ensure_ascii=False), media_type=media)
