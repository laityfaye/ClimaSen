"""Outil get_locality : une localite (village, quartier) et ses inondations.

Lit les fichiers sources de l'ANSD (jarvis/sources.py) :
  - localites RGPH-5 placees (script 33) : commune, coordonnees, precision du
    placement, jours de pluie extreme par an vecus par ses habitants ;
  - repertoire des localites : population aux recensements 1988, 2002, 2013
    et 2023 ;
  - inventaire des inondations documentees 2005-2020 du departement (source,
    page, extrait cite).

Historique prudent : les noms et les communes changent d'un recensement a
l'autre (reforme de 2013, homonymes). Une population passee n'est rattachee
que si UNE SEULE localite du departement porte ce nom cette annee-la ; sinon
l'outil dit "ambigu" plutot que d'additionner des homonymes.
"""
import difflib

from .. import sources as S
from .common import ToolInputError, arrondir, champ_texte

NAME = "get_locality"
LABEL = "Localité (village, quartier) et inondations documentées"
PERMISSION = "public"
DATASETS = ()

MAX_RESULTATS = 5
MAX_INONDATIONS = 8
ANNEES = (1988, 2002, 2013, 2023)

DESCRIPTION = (
    "Une LOCALITE du Senegal (village, quartier, hameau ; 25 317 au RGPH-5) : sa commune, "
    "son departement, sa population aux recensements 1988, 2002, 2013 et 2023 (ANSD), ses "
    "coordonnees et le nombre moyen de jours de pluie extreme par an (pixel CHIRPS > +2 "
    "sigma, 1981-2023), plus les INONDATIONS DOCUMENTEES de son departement (2005, 2009, "
    "2012, 2020 : source, page, extrait cite). Plusieurs localites portent souvent le meme "
    "nom : preciser department ou region. Avec department seul (sans name) : les "
    "inondations documentees du departement."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Nom de la localite (village, quartier)."},
        "department": {"type": "string", "description": "Departement, pour lever l'ambiguite."},
        "region": {"type": "string", "description": "Region, pour lever l'ambiguite."},
    },
}

LECTURE_JOURS = ("jours par an (1981-2023) ou le pixel CHIRPS de 0,25 deg de la localite "
                 "depasse +2 sigma un jour d'evenement ; mediane nationale 7,3")


def _cle(t):
    return S._cle(t)


def _inondations(departement):
    try:
        t = S.inondations()
    except S.SourceAbsente:
        return None
    sel = t[t["cle"] == _cle(departement)].sort_values(["annee", "certitude"])
    if sel.empty:
        return {"departement": departement, "evenements_documentes": [],
                "note": "aucune inondation documentee pour ce departement dans l'inventaire "
                        "2005-2020 (inventaire partiel : ce n'est pas une preuve d'absence)"}
    return {
        "departement": departement,
        "annees": sorted({int(a) for a in sel["annee"]}),
        "evenements_documentes": [
            {"annee": int(r["annee"]), "certitude": r["certitude"], "source": r["source"],
             "document": r["document"], "page": str(r["page_pdf"]),
             "extrait": str(r["extrait"])[:220]}
            for _, r in sel.head(MAX_INONDATIONS).iterrows()],
        "certitude": "A = le departement est nomme par la source ; B = indirect ou partiel",
        "inventaire": "inondations documentees 2005, 2009, 2012, 2020 (PDNA, UNOSAT, FICR, OCHA)",
    }


def _historique(rep, departement, nom):
    """Population par recensement, seulement si le nom est unique dans le departement."""
    sel = rep[(rep["cle"] == _cle(nom)) & (rep["Departement"].map(_cle) == _cle(departement))]
    histo, ambigus = {}, []
    for annee in ANNEES:
        lignes = sel[sel["Annee"] == annee]
        if len(lignes) == 1:
            histo[str(annee)] = int(lignes.iloc[0]["POPULATION"])
        elif len(lignes) > 1:
            ambigus.append(annee)
    return histo, ambigus


def _communes(loc, rep, nom, dep, reg):
    """Communes portant ce nom (agregat de leurs localites RGPH-5), et communes
    dont le nom commence par lui ("Touba" -> "Touba Mosquee")."""
    import numpy as np
    cles = loc["COMMUNE"].map(_cle)
    cle = _cle(nom)
    sel = loc[cles == cle]
    if dep:
        sel = sel[sel["Departement"].map(_cle) == _cle(dep)]
    if reg:
        sel = sel[sel["Region"].map(_cle) == _cle(reg)]
    fiches = []
    for (region, departement, commune), g in sel.groupby(["Region", "Departement", "COMMUNE"]):
        pop = g["POPULATION"].fillna(0)
        histo = {}
        r = rep[(rep["COMMUNE"].map(_cle) == cle)
                & (rep["Departement"].map(_cle) == _cle(departement))]
        for annee in ANNEES[:-1]:
            v = r.loc[r["Annee"] == annee, "POPULATION"].sum()
            if v > 0:
                histo[str(annee)] = int(v)
        histo["2023"] = int(pop.sum())
        fiches.append({
            "commune": str(commune).title(), "departement": str(departement).title(),
            "region": str(region).title(), "n_localites_ou_quartiers": int(len(g)),
            "population_par_recensement": histo,
            "menages_2023": int(g["MENAGE"].fillna(0).sum()),
            "jours_de_pluie_extreme_par_an": arrondir(
                float(np.average(g["jours_extremes_par_an"], weights=pop)) if pop.sum() > 0
                else float(g["jours_extremes_par_an"].mean()), 2),
            "note_historique": ("recensements anterieurs : somme des localites enregistrees "
                                "sous ce nom de commune ; le decoupage communal a change en "
                                "2013, comparer avec prudence"),
        })
    proches = sorted({str(c).title() for c, k in zip(loc["COMMUNE"], cles)
                      if k != cle and len(cle) >= 4 and k.startswith(cle)})[:6]
    return fiches, proches


def run(params, data):
    nom = champ_texte(params, "name", maxi=80)
    dep = champ_texte(params, "department", maxi=60)
    reg = champ_texte(params, "region", maxi=60)
    if not nom and not dep:
        raise ToolInputError("Donne name (localite) ou department.")
    if not nom:
        inond = _inondations(dep)
        if inond is None:
            raise ToolInputError("Inventaire des inondations absent de ce serveur.")
        return {"inondations_documentees": inond}
    try:
        loc = S.localites_placees()
        rep = S.repertoire()
    except S.SourceAbsente as exc:
        raise ToolInputError("Donnee absente de ce serveur : %s" % exc)

    communes, proches = _communes(loc, rep, nom, dep, reg)
    sel = loc[loc["cle"] == _cle(nom)]
    approche = False
    if sel.empty and communes:
        sortie = {"communes": communes,
                  "lecture_jours": LECTURE_JOURS + " ; commune : moyenne ponderee par la "
                                   "population de ses localites",
                  "source": "%s ; %s ; CHIRPS v2" % (S.SOURCE_LOCALITES, S.SOURCE_REPERTOIRE)}
        if len({c["departement"] for c in communes}) == 1:
            inond = _inondations(communes[0]["departement"])
            if inond is not None:
                sortie["inondations_documentees"] = inond
        return sortie
    if sel.empty:
        proches = difflib.get_close_matches(_cle(nom), loc["cle"].unique().tolist(), n=5,
                                            cutoff=0.85)
        sel = loc[loc["cle"].isin(proches)]
        approche = True
    if dep:
        sel = sel[sel["Departement"].map(_cle) == _cle(dep)]
    if reg:
        sel = sel[sel["Region"].map(_cle) == _cle(reg)]
    if sel.empty:
        raise ToolInputError("Aucune localite %r%s dans le RGPH-5 2023." % (
            nom, (" (departement %s)" % dep) if dep else ""))
    sel = sel.sort_values("POPULATION", ascending=False)

    resultats = []
    for _, r in sel.head(MAX_RESULTATS).iterrows():
        histo, ambigus = _historique(rep, r["Departement"], r["LOCALITE"])
        histo["2023"] = int(r["POPULATION"])
        fiche = {
            "localite": str(r["LOCALITE"]).title(), "commune": str(r["COMMUNE"]).title(),
            "departement": str(r["Departement"]).title(), "region": str(r["Region"]).title(),
            "population_par_recensement": histo,
            "menages_2023": int(r["MENAGE"]) if r["MENAGE"] == r["MENAGE"] else None,
            "coordonnees": {"lat": arrondir(r["LAT"], 4), "lon": arrondir(r["LON"], 4)},
            "precision_du_placement": r["precision"],
            "jours_de_pluie_extreme_par_an": arrondir(r["jours_extremes_par_an"], 2),
        }
        if ambigus:
            fiche["recensements_ambigus"] = (
                "%s : plusieurs localites de ce nom dans le departement, population non "
                "rattachee" % ", ".join(str(a) for a in ambigus))
        resultats.append(fiche)

    sortie = {
        "n_localites_trouvees": int(len(sel)),
        **({"communes_du_meme_nom": communes} if communes else {}),
        **({"communes_au_nom_proche": proches} if proches else {}),
        "localites": resultats,
        "lecture_jours": LECTURE_JOURS,
        "source": "%s ; %s ; CHIRPS v2" % (S.SOURCE_LOCALITES, S.SOURCE_REPERTOIRE),
    }
    if approche:
        sortie["note_nom"] = "nom approche : aucune localite ne porte exactement ce nom"
    if len(sel) > MAX_RESULTATS:
        sortie["ambiguite"] = ("%d localites portent ce nom : les %d plus peuplees sont "
                               "donnees ; preciser department ou region."
                               % (len(sel), MAX_RESULTATS))
    deps = list(dict.fromkeys(str(d) for d in sel.head(MAX_RESULTATS)["Departement"]))
    if len(deps) == 1:
        inond = _inondations(deps[0])
        if inond is not None:
            sortie["inondations_documentees"] = inond
    else:
        sortie["inondations_documentees"] = ("plusieurs departements : preciser department "
                                             "pour les inondations documentees")
    return sortie
