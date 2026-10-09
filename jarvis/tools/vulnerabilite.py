"""Outil get_priority_zones: quelles zones proteger en priorite ?

Lit l'indice de risque de pluies extremes (scripts 26 et 27) par le meme
chargeur que la page "Vulnerabilite" du dashboard (dashboard_utils.
load_vulnerabilite): Jarvis et la page donnent les memes chiffres.

Garde-fous: l'outil ne renvoie que des valeurs lues dans les CSV, chacune avec
sa source, et joint toujours la regle de lecture. L'indice CLASSE les zones
entre elles (rangs centiles): ce n'est ni une probabilite ni un nombre de
sinistres. La vulnerabilite est PROVISOIRE (pauvrete regionale EHCVM +
croissance 2013-2023) en attendant les donnees d'habitat du RGPH-5, et elle
place les zones de la region de Dakar au plus bas: le modele doit le dire
quand la question porte sur Dakar et sa banlieue.

La fiche d'une zone porte aussi, comme la page, ce qui vient de l'API SDMX de
l'ANSD (scripts 35-37) : population projetee 2026/2030, profondeur et severite
de la pauvrete, son evolution 2011-2022, et les communes du departement
(contours reconstruits, script 34). Ces chiffres N'ENTRENT PAS dans l'indice.
Jeux facultatifs : sans eux, la fiche reste celle de l'indice.
"""
from . import dataset
from .common import ToolInputError, arrondir, champ_enum, champ_entier, champ_texte, normalise

NAME = "get_priority_zones"
LABEL = "Zones prioritaires (indice de risque)"
PERMISSION = "public"
DATASETS = ("vulnerabilite",)

NIVEAUX = ("departements", "arrondissements")
COMPOSANTES = {
    "indice": "indice_risque",
    "alea": "A_alea",
    "exposition": "E_exposition",
    "vulnerabilite": "V_vulnerabilite",
}
LIBELLES = {
    "A_alea": "alea (frequence des pluies extremes, CHIRPS)",
    "E_exposition": "exposition (population et densite, ANSD RGPH-5)",
    "V_vulnerabilite": "vulnerabilite provisoire (pauvrete regionale EHCVM, croissance 2013-2023)",
}

DESCRIPTION = (
    "INDICE DE RISQUE de pluies extremes par zone du Senegal: 46 departements ou 125 "
    "arrondissements (contours OCHA). Indice = (Alea x Exposition x Vulnerabilite)^(1/3), "
    "chaque composante en rang centile de 0 (plus faible) a 1 (plus fort). Alea: jours/an "
    "d'anomalie > 2 sigma et jours >= 50 mm (CHIRPS 1981-2023, mai-octobre). Exposition: "
    "population et densite 2023 (ANSD RGPH-5). Vulnerabilite PROVISOIRE: pauvrete EHCVM "
    "2021-2022 de la region et croissance demographique 2013-2023. A utiliser pour 'quelles "
    "zones proteger en priorite', 'ou le risque d'inondation est-il le plus fort', 'classement "
    "des departements', 'pourquoi tel departement ressort', 'risque a Pikine'. Renvoie le "
    "classement (5 zones par defaut, filtrable par region), ou la fiche d'une zone avec "
    "zone=<nom> (chiffres bruts, indicateurs EHCVM de sa region, population projetee ANSD "
    "2026/2030, profondeur et severite de la pauvrete, et pour un departement ses communes : "
    "population 2023/2026, densite, jours de pluie extreme par an). Chaque reponse porte le "
    "bloc fiabilite (sensibilite aux poids, validation contre les inondations documentees "
    "2005-2020) et les donnees absentes : a utiliser pour 'l'indice est-il valide / fiable / "
    "robuste'."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "enum": list(NIVEAUX),
                  "description": "Echelle: departements (defaut) ou arrondissements."},
        "component": {"type": "string", "enum": list(COMPOSANTES),
                      "description": "Classer par l'indice (defaut) ou par une composante."},
        "top": {"type": "integer", "minimum": 1, "maximum": 20,
                "description": "Nombre de zones a renvoyer (defaut 10)."},
        "region": {"type": "string",
                   "description": "Restreindre le classement a une region (ex. Dakar, Kolda)."},
        "zone": {"type": "string",
                 "description": "Nom d'un departement ou d'un arrondissement: renvoie sa fiche "
                                "et son rang."},
    },
}

REGLE = (
    "Chiffres de cette reponse seulement, avec leur source. L'indice CLASSE les zones (rang "
    "centile 0-1) : ni probabilite, ni nombre de sinistres, ni prevision de saison "
    "(get_seasonal_outlook). Par zone citee : rang, indice, composante_dominante. Reserve "
    "obligatoire, une fois : vulnerabilite provisoire (pauvrete regionale EHCVM, croissance "
    "2013-2023). Si on demande si l'indice est valide, fiable ou robuste : cite le bloc "
    "fiabilite tel quel (AUC face aux inondations documentees, top 10 stable). Dakar et sa "
    "banlieue sortent bas : pauvrete regionale la plus basse, croissance recente faible ; poids "
    "non ajustes. Indicateurs EHCVM : echelle regionale, a dire. Aucune mesure de protection "
    "chiffree."
)

SOURCES = (
    "alea : CHIRPS v2 0,25 deg, 1981-2023, mai-octobre | population : ANSD RGPH-5 2023 et "
    "RGPH 2013 | pauvrete et indicateurs regionaux : ANSD EHCVM 2021-2022 (Tab. III-2, VII-11, "
    "Carte VII-1, Fig. VIII-3, VIII-6) ; profondeur, severite et evolution de la pauvrete, "
    "population projetee 2026-2030 : ANSD, API SDMX (Open Data Platform), taux 2011 : ESPS "
    "| communes : contours "
    "approximatifs reconstruits des coordonnees des localites ANSD (script 34) | contours : "
    "OCHA COD-AB v02 (2024) | validation : "
    "inondations 2005-2020 (PDNA 2009, UNOSAT, FICR, OCHA), script 29"
)

HORS_INDICE = ("donnees de l'API SDMX de l'ANSD : elles n'entrent PAS dans l'indice (qui "
               "garde la pauvrete EHCVM 2021-2022 et la population 2023) ; elles le "
               "completent")
LECTURE_COMMUNES = ("contours APPROXIMATIFS (limite a mi-distance des localites voisines), "
                    "pas les limites officielles ; l'indice n'est pas calcule a la commune ; "
                    "jours_extremes_par_an = jours par an ou le pixel CHIRPS des habitants "
                    "depasse +2 sigma, moyenne ponderee par la population")
MAX_COMMUNES = 8

# Donnees que la plateforme N'A PAS (pour repondre franchement aux experts).
DONNEES_ABSENTES = (
    "pauvrete par departement ou par milieu dans chaque region (microdonnees EHCVM, ANADS) ; "
    "habitat RGPH-5 par departement (logement, assainissement, evacuation des eaux) ; "
    "valeurs par departement de l'Atlas RGPH-5 (seules les classes extremes sont publiees)"
)


def _fiabilite(v, niveau):
    """Sensibilite aux poids et validation historique (script 29), ou None."""
    r = v.get("robustesse")
    if not r:
        return None
    sens = next((x for x in r.get("sensibilite", []) if x.get("niveau") == niveau), None)
    sortie = {}
    if sens:
        sortie["sensibilite_aux_poids"] = {
            "variantes_testees": len(r.get("variantes", {})) or 6,
            "spearman_avec_indice_publie_min": sens.get("spearman_vs_publie_min"),
            "zones_du_top10_communes_a_toutes_les_variantes": sens.get("top10_communs"),
        }
    val = (r.get("validation") or {}).get("indice_publie") or {}
    une = val.get("au moins une (A)")
    deux = val.get("2 evenements ou plus (A)")
    if une and niveau != "departements":
        sortie["validation_inondations_documentees"] = (
            "faite au niveau departement seulement (voir level=departements)")
    if une and niveau == "departements":
        sortie["validation_inondations_documentees"] = {
            "auc_departements_touches_au_moins_une_fois": une["auc"],
            "ic95": [une["ic95_bas"], une["ic95_haut"]],
            "n_touches": une["n_touches"],
            "auc_touches_deux_fois_ou_plus": deux["auc"] if deux else None,
            "lecture": "0,5 = hasard ; l'indice ne retrouve pas les departements inondes "
                       "documentes (surtout urbains) ; l'exposition seule les distingue mieux",
        }
        auc = v.get("robustesse_auc")
        comp = {}
        if auc is not None:
            sel = auc[auc["groupe"] == "au moins une (A)"]
            # Libelles du CSV (script 29) -> cles lisibles.
            for var, cle in (("Exposition seule", "exposition_seule"),
                             ("Al\u00e9a seul", "alea_seul"),
                             ("Vuln\u00e9rabilit\u00e9 seule", "vulnerabilite_seule")):
                ligne = sel[sel["variable"] == var]
                if len(ligne):
                    comp[cle] = arrondir(ligne.iloc[0]["auc"], 2)
        if comp:
            sortie["validation_inondations_documentees"]["auc_par_composante"] = comp
    return sortie or None


def _indicateurs_region(v, region):
    """Indicateurs EHCVM de la region (transcrits du rapport), ou None."""
    cle = normalise(region)
    sortie = {}
    for nom, cols in (("ehcvm_assainissement", ("fosse_rudimentaire_trou_ouvert_pct",
                                                "wc_chasse_eau_pct")),
                      ("ehcvm_services", ("acces_electricite_menages_pct",
                                          "insecurite_alimentaire_moderee_ou_grave_pct",
                                          "menages_ayant_subi_un_choc_3_ans_pct"))):
        t = v.get(nom)
        if t is None:
            continue
        ligne = t[t["region"].map(normalise) == cle]
        if len(ligne):
            for c in cols:
                sortie[c] = arrondir(ligne.iloc[0][c], 1)
    if sortie:
        sortie["echelle"] = "region (EHCVM 2021-2022), meme valeur pour toutes ses zones"
    return sortie or None


def _complements_ansd(data, r, niveau):
    """Ce que la fiche de la page Vulnerabilite montre en plus de l'indice :
    projection de population, pauvrete detaillee, communes. None si rien."""
    pcode = str(r["pcode"])
    sortie = {}
    proj = dataset.facultatif(data, "population_projetee")
    if proj is not None and niveau == "departements" and pcode in proj.index:
        ligne = proj.loc[pcode]
        sortie["population_projetee"] = {
            "2023": int(ligne["population_2023"]), "2026": int(ligne["population_2026"]),
            "2030": int(ligne["population_2030"])}
    pauv = (dataset.facultatif(data, "pauvrete_ansd") or {}).get(pcode[:4])
    if pauv:
        bloc = {"echelle": "region"}
        for cle, nom in (("taux", "taux_P0_2022_pct"), ("profondeur", "profondeur_P1_2022_pct"),
                         ("severite", "severite_P2_2022_pct"), ("taux_2011", "taux_P0_2011_pct"),
                         ("taux_2019", "taux_P0_2019_pct")):
            if cle in pauv:
                bloc[nom] = arrondir(pauv[cle], 1)
        sortie["pauvrete_region"] = bloc
    if niveau == "departements":
        communes = _communes_du_departement(data, pcode, proj)
        if communes:
            sortie["communes"] = communes
    elif niveau == "arrondissements":
        sortie["communes"] = ("liste des communes : fiche du departement (level=departements, "
                              "zone=%s)" % r.get("departement"))
    if sortie:
        sortie["statut"] = HORS_INDICE
    return sortie or None


def _communes_du_departement(data, pcode, proj):
    geo = dataset.facultatif(data, "communes")
    if not geo:
        return None
    lignes = [f["properties"] for f in geo.get("features", [])
              if f["properties"].get("adm2_pcode") == pcode]
    if not lignes:
        return None
    from .dataset import _utils
    code = _utils().code_commune
    lignes.sort(key=lambda c: -(c.get("population_2023") or 0))
    detail = []
    for c in lignes[:MAX_COMMUNES]:
        d = {"commune": str(c.get("commune_ansd", "")).title(),
             "population_2023": c.get("population_2023"),
             "densite_hab_km2": arrondir(c.get("densite_hab_km2"), 0),
             "jours_extremes_par_an": arrondir(c.get("jours_extremes_par_an"), 2)}
        if proj is not None:
            k = code(pcode, c.get("commune_ansd", ""))
            if k in proj.index:
                d["population_2026"] = int(proj.loc[k, "population_2026"])
        detail.append(d)
    jours = [c["jours_extremes_par_an"] for c in lignes if c.get("jours_extremes_par_an") is not None]
    return {
        "nombre": len(lignes),
        "par_population_decroissante": detail,
        "jours_extremes_par_an_min_max": ([arrondir(min(jours), 2), arrondir(max(jours), 2)]
                                          if jours else None),
        "lecture": LECTURE_COMMUNES,
    }


def _niveau(params):
    brut = params.get("level")
    if brut is None:
        return "departements"
    cle = normalise(brut)
    if cle in ("departement", "departements", "dep", "admin2"):
        return "departements"
    if cle in ("arrondissement", "arrondissements", "arr", "admin3"):
        return "arrondissements"
    raise ToolInputError("level inconnu: %r. Valeurs acceptees: %s." % (brut, ", ".join(NIVEAUX)))


def _fiche(r, niveau, n):
    comps = {c: arrondir(r[c], 3) for c in LIBELLES}
    dominante = max(LIBELLES, key=lambda c: -1 if r[c] != r[c] else r[c])
    faible = min(LIBELLES, key=lambda c: 2 if r[c] != r[c] else r[c])
    fiche = {
        "rang_indice": int(r["rang"]) if r["rang"] == r["rang"] else None,
        "sur": n,
        "nom": r["nom"],
        "pcode": r["pcode"],
        "region": r["region"],
        "indice_risque": arrondir(r["indice_risque"], 3),
        "alea": comps["A_alea"],
        "exposition": comps["E_exposition"],
        "vulnerabilite_provisoire": comps["V_vulnerabilite"],
        "composante_dominante": LIBELLES[dominante],
        "composante_la_plus_faible": LIBELLES[faible],
        "chiffres_bruts": {
            "jours_par_an_anomalie_sup_2sigma": arrondir(r["jours_anomalie_2sigma_an"], 2),
            "jours_par_an_pluie_sup_50mm": arrondir(r["jours_50mm_an"], 2),
            "population_2023": int(r["population_2023"]),
            "population_2013": int(r["population_2013"]),
            "croissance_2013_2023_pct": arrondir(r["croissance_2013_2023_pct"], 1),
            "superficie_km2": arrondir(r["superficie_km2"], 1),
            "densite_2023_hab_km2": arrondir(r["densite_2023_hab_km2"], 0),
            "taux_pauvrete_region_pct": arrondir(r["taux_pauvrete_region_pct"], 1),
            "pauvres_estimes_2023": int(round(r["pauvres_estimes_2023"])),
        },
    }
    if str(r.get("methode_alea", "")).startswith("pixel terrestre"):
        fiche["note_alea"] = ("zone plus petite qu'un pixel CHIRPS: alea du pixel terrestre "
                              "le plus proche, partage avec les zones voisines")
    if niveau == "arrondissements":
        fiche["departement"] = r["departement"]
        fiche["indice_du_departement"] = arrondir(r.get("indice_departement"), 3)
        fiche["rang_du_departement_sur_46"] = (int(r["rang_departement"])
                                               if r.get("rang_departement") == r.get("rang_departement")
                                               else None)
    return fiche


def _ligne(r, niveau, n):
    """Version courte de la fiche, pour les classements."""
    f = _fiche(r, niveau, n)
    b = f.pop("chiffres_bruts")
    f.pop("composante_la_plus_faible", None)
    f.pop("sur", None)  # deja dans nombre_de_zones
    f.pop("indice_du_departement", None)       # dans la fiche complete (zone=)
    f.pop("rang_du_departement_sur_46", None)
    # Libelle court : la definition de chaque composante est dans la formule.
    f["composante_dominante"] = f["composante_dominante"].split(" (")[0]
    f["population_2023"] = b["population_2023"]
    f["taux_pauvrete_region_pct"] = b["taux_pauvrete_region_pct"]
    return f


def run(params, data):
    v = data["vulnerabilite"]
    niveau = _niveau(params)
    t = v["departements"] if niveau == "departements" else v["arrondissements"]
    if t is None:
        raise ToolInputError("L'indice par arrondissement n'a pas ete calcule "
                             "(scripts/27_indice_risque_arrondissements.py). Utilise level="
                             "departements.")
    t = t.copy()
    t["nom"] = (t["departement"] if niveau == "departements" else t["arrondissement"]).fillna(
        "Sans nom")
    composante = champ_enum(params, "component", list(COMPOSANTES), defaut="indice")
    colonne = COMPOSANTES[composante]
    top = champ_entier(params, "top", mini=1, maxi=20, defaut=5)
    region = champ_texte(params, "region", maxi=40)
    zone = champ_texte(params, "zone", maxi=60)
    n = int(len(t))

    resultat = {
        "niveau": niveau,
        "nombre_de_zones": n,
        "formule": "indice = (alea x exposition x vulnerabilite)^(1/3), rangs centiles 0-1",
        "statut_vulnerabilite": "provisoire en attendant les donnees d'habitat RGPH-5",
        "regle_interpretation": REGLE,
        "sources": SOURCES,
    }

    if zone:
        cle = normalise(zone)
        trouves = t[t["nom"].map(normalise) == cle]
        if trouves.empty:
            trouves = t[t["nom"].map(normalise).str.contains(cle, regex=False)]
        if trouves.empty:
            autre = "arrondissements" if niveau == "departements" else "departements"
            raise ToolInputError(
                "Zone inconnue au niveau %s: %r. Essaie level=%s, ou un nom parmi: %s."
                % (niveau, zone, autre, ", ".join(sorted(t["nom"].astype(str))[:60])))
        resultat["zones"] = [_fiche(r, niveau, n) for _, r in trouves.head(5).iterrows()]
        indic = _indicateurs_region(v, trouves.iloc[0]["region"])
        if indic:
            resultat["indicateurs_region_ehcvm"] = indic
        ansd = _complements_ansd(data, trouves.iloc[0], niveau)
        if ansd:
            resultat["complements_ansd"] = ansd
        resultat["fiabilite"] = _fiabilite(v, niveau)
        resultat["donnees_absentes"] = DONNEES_ABSENTES
        return resultat

    if region:
        cle = normalise(region)
        sous = t[t["region"].map(normalise) == cle]
        if sous.empty:
            raise ToolInputError("Region inconnue: %r. Valeurs acceptees: %s."
                                 % (region, ", ".join(sorted(t["region"].unique()))))
        t = sous
        resultat["region"] = t["region"].iloc[0]
        resultat["note_region"] = ("rangs nationaux (sur %d); le classement ci-dessous est "
                                   "restreint a la region" % n)

    t = t.sort_values(colonne, ascending=False)
    resultat["classe_par"] = composante
    resultat["zones"] = [_ligne(r, niveau, n) for _, r in t.head(top).iterrows()]
    resultat["detail"] = "fiche complete d'une zone (chiffres bruts, EHCVM) : parametre zone"
    # Repere pour la limite connue: la region de Dakar a la pauvrete la plus basse.
    dakar = v["departements"]
    pauv_min = dakar.loc[dakar["taux_pauvrete_region_pct"].idxmin()]
    resultat["repere_pauvrete_la_plus_basse"] = {
        "region": pauv_min["region"],
        "taux_pauvrete_region_pct": arrondir(pauv_min["taux_pauvrete_region_pct"], 1),
    }
    resultat["fiabilite"] = _fiabilite(v, niveau)
    resultat["donnees_absentes"] = DONNEES_ABSENTES
    return resultat
