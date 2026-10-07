"""Figures a la demande: une grammaire bornee, pas du code.

Quand aucun visuel existant ne repond (figure de reference, make_figure,
show_map), le modele decrit la figure voulue en JSON; ce moteur la valide
puis la calcule avec pandas, et la rend avec jarvis/figures (memes palettes,
meme vue CSV). Le modele ne fournit jamais de code.

    {"dataset": "departements",
     "filters": [{"column": "region", "op": "=", "value": "Dakar"}],
     "mark": "barres_horizontales", "x": "departement", "y": "population_2023",
     "sort": "desc", "top": 10}

Garde-fous (refus motive, que le modele peut corriger):
  - jeux et colonnes du catalogue (catalogue.yaml) seulement;
  - agregation compatible avec la nature de la colonne (pas de moyenne de
    rangs, pas de somme de densites);
  - effectifs minimaux (10 points pour un nuage, 5 par boite);
  - echelle de couleur imposee par le type de donnee (la carte de chaleur est
    reservee aux correlations, divergente et centree sur 0);
  - taux d'appariement des jointures affiche, jointure refusee sous 50 %;
  - titre et commentaire du modele sans chiffre (sauf annees): les valeurs
    viennent des donnees, jamais du texte.
Titre, unite, periode et source sont remplis par le catalogue.
"""
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import PROJECT_DIR


def normalise(texte):
    # Import differe: jarvis.tools importe ce module (outil make_custom_figure).
    from ..tools.common import normalise as _n
    return _n(texte)

CATALOGUE = Path(__file__).resolve().parent / "catalogue.yaml"
MARQUES = ("barres", "barres_horizontales", "courbes", "nuage", "boites", "carte",
           "carte_chaleur", "tableau")
OPERATEURS = ("=", "!=", "<", "<=", ">", ">=", "in", "contains")
AGREGATIONS = ("somme", "moyenne", "mediane", "min", "max", "comptage")
PERMISES = {
    "stock": ("somme", "moyenne", "mediane", "min", "max"),
    "mesure": ("moyenne", "mediane", "min", "max"),
    "taux": ("moyenne", "mediane", "min", "max"),
    "rang": ("mediane", "min", "max"),
    "correlation": ("mediane", "min", "max"),
    "probabilite": ("min", "max"),
    "annee": ("min", "max"), "mois": ("min", "max"),
}
NUMERIQUES = ("stock", "mesure", "taux", "rang", "correlation", "probabilite", "annee", "mois")
GROUPABLES = ("categorie", "annee", "mois", "code")
FONCTIONS = {"somme": "sum", "moyenne": "mean", "mediane": "median", "min": "min", "max": "max"}
LIBELLES_AGREG = {"somme": "somme", "moyenne": "moyenne", "mediane": "médiane", "min": "minimum",
                  "max": "maximum", "comptage": "nombre"}
MAX_FILTRES = 6
MAX_CATEGORIES = 30
MAX_TEMPOREL = 60          # barres par annee: 43 saisons tiennent
MAX_SERIES = 4
MAX_BOITES = 12
MIN_NUAGE = 10
MIN_BOITE = 5
MAX_COLONNES_TABLEAU = 8
_ANNEE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


class SpecInvalide(ValueError):
    """Specification refusee; le message dit pourquoi et ce qui est accepte."""


@lru_cache(maxsize=1)
def catalogue() -> dict:
    import yaml
    return yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))


def resume_catalogue() -> dict:
    """Description courte des jeux et colonnes, pour le modele."""
    return {nom: {"description": j["description"],
                  "colonnes": {c: m["nature"] for c, m in j["colonnes"].items()}}
            for nom, j in catalogue()["jeux"].items()}


_verrou = threading.Lock()
_cache = {}


def charger_jeu(nom) -> pd.DataFrame:
    jeux = catalogue()["jeux"]
    if nom not in jeux:
        raise SpecInvalide("Jeu de donnees inconnu : %r. Jeux disponibles : %s."
                           % (nom, ", ".join(sorted(jeux))))
    with _verrou:
        if nom in _cache:
            return _cache[nom]
    j = jeux[nom]
    genre, _, cible = j["chargeur"].partition(":")
    if genre == "fichier":
        df = pd.read_csv(PROJECT_DIR / cible, encoding="utf-8")
    else:
        from ..tools import dataset
        racine, _, cle = cible.partition(".")
        brut = dataset.get(racine)
        if cle:
            brut = brut[cle]
        if racine == "correlations":
            df = pd.concat([t.assign(phase=p) for p, t in brut.items()], ignore_index=True)
        elif j.get("transformation") == "annuelle":
            df = brut.assign(annee=brut["date"].dt.year).drop(columns=["date"]) \
                .groupby("annee", as_index=False).mean()
        else:
            df = brut
    colonnes = [c for c in j["colonnes"] if c in df.columns]
    df = df[colonnes].copy()
    with _verrou:
        _cache[nom] = df
    return df


# =============================================================================
# Validation
# =============================================================================
def _texte_libre(valeur, nom, maxi):
    if valeur is None:
        return ""
    texte = str(valeur).strip()
    if len(texte) > maxi:
        raise SpecInvalide("%s trop long (%d caracteres au plus)." % (nom, maxi))
    sans_annees = _ANNEE.sub("", texte)
    if re.search(r"\d", sans_annees):
        raise SpecInvalide("%s ne doit contenir aucun chiffre (hors annees) : les valeurs "
                           "viennent des donnees, pas du texte." % nom)
    return texte


class Plan:
    """Specification validee: jeu, colonnes et leurs metadonnees."""

    def __init__(self, brute):
        if not isinstance(brute, dict):
            raise SpecInvalide("La specification doit etre un objet JSON.")
        cat = catalogue()
        self.jeu = brute.get("dataset")
        if self.jeu not in cat["jeux"]:
            raise SpecInvalide("dataset inconnu : %r. Jeux disponibles : %s."
                               % (self.jeu, ", ".join(sorted(cat["jeux"]))))
        self.meta_jeu = cat["jeux"][self.jeu]
        self.colonnes = {c: dict(m) for c, m in self.meta_jeu["colonnes"].items()}
        self.jointure = None
        jointure = brute.get("join")
        if jointure:
            droite = jointure.get("dataset") if isinstance(jointure, dict) else jointure
            autorisees = [j for j in cat.get("jointures", [])
                          if j["gauche"] == self.jeu and j["droite"] == droite]
            if not autorisees:
                possibles = [j["droite"] for j in cat.get("jointures", []) if j["gauche"] == self.jeu]
                raise SpecInvalide("Jointure %s -> %r non autorisee. Possibles : %s."
                                   % (self.jeu, droite, ", ".join(possibles) or "aucune"))
            self.jointure = autorisees[0]
            for c, m in cat["jeux"][droite]["colonnes"].items():
                self.colonnes["%s.%s" % (droite, c)] = dict(m)
        self.marque = brute.get("mark")
        if self.marque not in MARQUES:
            raise SpecInvalide("mark inconnu : %r. Valeurs acceptees : %s."
                               % (self.marque, ", ".join(MARQUES)))
        self.filtres = self._filtres(brute.get("filters") or [])
        self.x = self._col(brute.get("x"), "x")
        self.y = self._col(brute.get("y"), "y")
        self.series = self._col(brute.get("series"), "series")
        self.group_by = self._col(brute.get("group_by"), "group_by")
        self.label = self._col(brute.get("label"), "label")
        self.mesure = brute.get("measure")
        if self.mesure not in (None, "comptage"):
            self.mesure = self._col(self.mesure, "measure")
        self.agregation = brute.get("aggregation")
        if self.agregation is not None and self.agregation not in AGREGATIONS:
            raise SpecInvalide("aggregation inconnue : %r. Valeurs acceptees : %s."
                               % (self.agregation, ", ".join(AGREGATIONS)))
        self.tri = brute.get("sort")
        if self.tri not in (None, "asc", "desc"):
            raise SpecInvalide("sort vaut asc ou desc.")
        top = brute.get("top")
        if top is not None:
            try:
                top = int(top)
            except (TypeError, ValueError):
                raise SpecInvalide("top doit etre un entier.")
            if not 1 <= top <= MAX_CATEGORIES:
                raise SpecInvalide("top entre 1 et %d." % MAX_CATEGORIES)
        self.top = top
        cols = brute.get("columns") or []
        if not isinstance(cols, list):
            raise SpecInvalide("columns doit etre une liste.")
        self.colonnes_tableau = [self._col(c, "columns") for c in cols]
        self.surligne = [str(s) for s in (brute.get("highlight") or [])][:12]
        self.titre = _texte_libre(brute.get("title"), "title", 90)
        self.commentaire = _texte_libre(brute.get("caption"), "caption", 300)
        self._coherence()

    def _col(self, nom, role):
        if nom is None:
            return None
        if nom not in self.colonnes:
            raise SpecInvalide("Colonne inconnue pour %s : %r. Colonnes de %s : %s."
                               % (role, nom, self.jeu, ", ".join(sorted(self.colonnes))))
        return nom

    def nature(self, col):
        return self.colonnes[col]["nature"]

    def libelle(self, col):
        if col == "comptage":
            return "nombre d'événements" if self.jeu == "evenements" else "nombre"
        return self.colonnes[col].get("libelle", col)

    def unite(self, col):
        if col == "comptage":
            return "nombre d'événements" if self.jeu == "evenements" else "nombre de lignes"
        return self.colonnes[col].get("unite", "sans unité")

    def _filtres(self, filtres):
        if not isinstance(filtres, list) or len(filtres) > MAX_FILTRES:
            raise SpecInvalide("filters : liste de %d conditions au plus." % MAX_FILTRES)
        sortie = []
        for f in filtres:
            if not isinstance(f, dict):
                raise SpecInvalide("Chaque filtre est un objet {column, op, value}.")
            col = self._col(f.get("column"), "filters")
            op = f.get("op", "=")
            if op not in OPERATEURS:
                raise SpecInvalide("op inconnu : %r. Valeurs acceptees : %s."
                                   % (op, ", ".join(OPERATEURS)))
            if op in ("<", "<=", ">", ">=") and self.nature(col) not in NUMERIQUES:
                raise SpecInvalide("Comparaison %s impossible sur la colonne textuelle %s."
                                   % (op, col))
            if op == "in" and not isinstance(f.get("value"), list):
                raise SpecInvalide("op 'in' attend une liste de valeurs.")
            sortie.append((col, op, f.get("value")))
        return sortie

    def _numerique(self, col, role):
        if col is None:
            raise SpecInvalide("%s est requis pour mark=%s." % (role, self.marque))
        if self.nature(col) not in NUMERIQUES:
            raise SpecInvalide("%s doit etre une colonne numerique (%s est de nature %s)."
                               % (role, col, self.nature(col)))

    def _coherence(self):
        m = self.marque
        if m in ("barres", "barres_horizontales"):
            if self.group_by:
                if self.nature(self.group_by) not in GROUPABLES:
                    raise SpecInvalide("group_by doit etre une categorie, une annee ou un mois.")
                if self.mesure is None:
                    raise SpecInvalide("measure est requis avec group_by (une colonne, ou "
                                       "'comptage').")
                if self.mesure != "comptage":
                    self._agregation_permise(self.mesure)
            else:
                if not self.x or self.nature(self.x) not in GROUPABLES:
                    raise SpecInvalide("Barres sans group_by : x doit etre une categorie (ex. "
                                       "departement) et y une colonne numerique.")
                self._numerique(self.y, "y")
        elif m == "courbes":
            if not self.x or self.nature(self.x) not in ("annee", "mois") + NUMERIQUES:
                raise SpecInvalide("Courbes : x doit etre une annee, un mois ou un nombre.")
            self._numerique(self.y, "y")
            if self.series and self.nature(self.series) not in ("categorie",):
                raise SpecInvalide("series doit etre une categorie.")
            if self.agregation:
                self._agregation_permise(self.y)
        elif m == "nuage":
            self._numerique(self.x, "x")
            self._numerique(self.y, "y")
        elif m == "boites":
            if not self.group_by or self.nature(self.group_by) not in GROUPABLES:
                raise SpecInvalide("Boites : group_by (categorie) est requis.")
            self._numerique(self.y, "y")
        elif m == "carte":
            geo = self.meta_jeu.get("geo")
            if not geo:
                avec = [n for n, j in catalogue()["jeux"].items() if j.get("geo")]
                raise SpecInvalide("Carte impossible pour %s : jeux cartographiables : %s."
                                   % (self.jeu, ", ".join(avec)))
            self._numerique(self.y, "y")
            if self.nature(self.y) in ("correlation", "probabilite", "annee", "mois"):
                raise SpecInvalide("Carte : la colonne %s (%s) n'est pas une grandeur "
                                   "cartographiable." % (self.y, self.nature(self.y)))
        elif m == "carte_chaleur":
            if self.jeu != "correlations":
                raise SpecInvalide("carte_chaleur est reservee aux correlations (echelle "
                                   "divergente centree sur 0) ; utilise des barres ou une carte.")
            if not (self.x and self.series and self.y):
                raise SpecInvalide("carte_chaleur : x (colonnes, ex. lag_months), series "
                                   "(lignes, ex. index) et y (valeur) sont requis.")
            if self.nature(self.y) != "correlation":
                raise SpecInvalide("carte_chaleur : y doit etre une correlation.")
        elif m == "tableau":
            if not self.colonnes_tableau or len(self.colonnes_tableau) > MAX_COLONNES_TABLEAU:
                raise SpecInvalide("tableau : columns, de 1 a %d colonnes."
                                   % MAX_COLONNES_TABLEAU)

    def _agregation_permise(self, col):
        nature = self.nature(col)
        if not self.agregation:
            raise SpecInvalide("aggregation est requise pour %s. Permises pour une colonne de "
                               "nature %s : %s." % (col, nature, ", ".join(PERMISES.get(nature, ()))))
        if self.agregation == "comptage":
            return
        if self.agregation not in PERMISES.get(nature, ()):
            raise SpecInvalide(
                "Agregation %r interdite pour %s (nature %s) : %s. Permises : %s."
                % (self.agregation, col, nature, {
                    "rang": "une moyenne de rangs centiles n'a pas de sens",
                    "taux": "on n'additionne pas des taux ou des densites",
                    "mesure": "on n'additionne pas des intensites",
                    "correlation": "on ne moyenne ni n'additionne des correlations",
                    "probabilite": "on ne moyenne pas des p-values"}.get(nature, "non pertinente"),
                   ", ".join(PERMISES.get(nature, ())) or "aucune"))


# =============================================================================
# Calcul
# =============================================================================
def _appliquer_filtres(df, plan):
    for col, op, val in plan.filtres:
        serie = df[col]
        if op in ("=", "!=", "contains", "in") and plan.nature(col) in ("categorie", "code"):
            norm = serie.fillna("").map(normalise)
            if op == "in":
                cibles = {normalise(v) for v in val}
                masque = norm.isin(cibles)
            elif op == "contains":
                masque = norm.str.contains(normalise(val), regex=False)
            else:
                masque = norm == normalise(val)
                if op == "!=":
                    masque = ~masque
        else:
            try:
                if op == "in":
                    masque = serie.isin([float(v) for v in val])
                else:
                    v = float(val)
                    masque = {"=": serie == v, "!=": serie != v, "<": serie < v, "<=": serie <= v,
                              ">": serie > v, ">=": serie >= v}[op]
            except (TypeError, ValueError, KeyError):
                raise SpecInvalide("Filtre %s %s %r : valeur numerique attendue." % (col, op, val))
        df = df[masque]
    return df


def _joindre(df, plan, notes):
    j = plan.jointure
    droite = charger_jeu(j["droite"]).copy()
    droite.columns = ["%s.%s" % (j["droite"], c) for c in droite.columns]
    cle_d = "%s.%s" % (j["droite"], j["cle_droite"])
    droite["__cle"] = droite[cle_d].fillna("").map(normalise)
    if droite["__cle"].duplicated().any():
        raise SpecInvalide("Jointure ambigue : plusieurs lignes de %s par cle." % j["droite"])
    gauche = df.copy()
    gauche["__cle"] = gauche[j["cle_gauche"]].fillna("").map(normalise)
    fusion = gauche.merge(droite, on="__cle", how="left")
    n = len(gauche)
    apparies = int(fusion[cle_d].notna().sum()) if n else 0
    taux = apparies / float(n) if n else 0.0
    notes["appariement"] = {"apparies": apparies, "total": n, "taux": round(taux, 3)}
    if taux < 0.5:
        raise SpecInvalide("Jointure %s -> %s : seulement %d lignes sur %d appariees : resultat "
                           "non fiable." % (plan.jeu, j["droite"], apparies, n))
    return fusion.drop(columns=["__cle"])


def _agreger(groupe, col, agregation):
    if agregation == "comptage" or col == "comptage":
        return groupe.size()
    return groupe[col].agg(FONCTIONS[agregation])


def _arrondi(v, d=3):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, d) if np.isfinite(f) else None


def _periode(plan, df):
    col = plan.meta_jeu.get("annee")
    if col and col in df.columns and len(df):
        a, b = int(df[col].min()), int(df[col].max())
        return "%d-%d" % (a, b) if a != b else str(a)
    return str(plan.meta_jeu["periode"])


def executer(brute) -> dict:
    """Valide puis calcule. Renvoie un dict:
    genre ('figure' ou 'tableau'), spec (pour jarvis/figures) ou colonnes/lignes,
    titre, legende, unite, periode, source, resume."""
    plan = Plan(brute)
    notes = {}
    df = charger_jeu(plan.jeu)
    if plan.jointure:
        df = _joindre(df, plan, notes)
    df = _appliquer_filtres(df, plan)
    if df.empty:
        raise SpecInvalide("Aucune ligne ne correspond aux filtres.")
    m = plan.marque
    provisoires = sorted({plan.libelle(c) for c in (plan.x, plan.y, plan.mesure, plan.group_by)
                          if c and c != "comptage" and plan.colonnes[c].get("provisoire")})
    resume = {"jeu": plan.jeu, "lignes_retenues": int(len(df))}
    sortie = {"genre": "figure"}

    if m in ("barres", "barres_horizontales"):
        if plan.group_by:
            agg = plan.agregation or "comptage"
            serie = _agreger(df.groupby(plan.group_by), plan.mesure, agg)
            y_lib, y_unite = (plan.libelle(plan.mesure) if plan.mesure != "comptage"
                              else plan.libelle("comptage")), plan.unite(plan.mesure)
            desc = "%s de %s par %s" % (LIBELLES_AGREG[agg].capitalize(), y_lib,
                                        plan.libelle(plan.group_by)) if agg != "comptage" \
                else "Nombre par %s" % plan.libelle(plan.group_by)
            x_lib = plan.libelle(plan.group_by)
        else:
            if df[plan.x].duplicated().any():
                raise SpecInvalide("Plusieurs lignes par valeur de %s : utilise group_by et une "
                                   "aggregation." % plan.x)
            serie = df.set_index(plan.x)[plan.y]
            y_lib, y_unite, x_lib = plan.libelle(plan.y), plan.unite(plan.y), plan.libelle(plan.x)
            desc = "%s par %s" % (y_lib.capitalize(), x_lib)
        serie = serie.dropna()
        if plan.tri or plan.top:
            serie = serie.sort_values(ascending=(plan.tri == "asc"))
        elif plan.nature(plan.group_by or plan.x) not in ("annee", "mois"):
            serie = serie.sort_values(ascending=False)
        if plan.top:
            serie = serie.head(plan.top)
        plafond = MAX_TEMPOREL if plan.nature(plan.group_by or plan.x) in ("annee", "mois")             else MAX_CATEGORIES
        if len(serie) > plafond:
            raise SpecInvalide("%d categories : trop pour une figure lisible (%d au plus). Ajoute "
                               "top ou un filtre." % (len(serie), plafond))
        horizontal = m == "barres_horizontales"
        cats = [str(int(c)) if isinstance(c, (int, np.integer, float)) and float(c).is_integer()
                else str(c) for c in serie.index]
        sortie["spec"] = {"genre": "barres",
                          "hauteur_pouces": max(1.9, 0.24 * len(cats) + 0.6) if horizontal else 2.4,
                          "donnees": {"categories": cats,
                                      "valeurs": [_arrondi(v) for v in serie.values],
                                      "x_label": x_lib, "y_label": y_lib, "horizontal": horizontal,
                                      "virgule": True}}
        unite = y_unite
        resume["valeurs"] = dict(list(zip(cats, [_arrondi(v) for v in serie.values]))[:10])

    elif m == "courbes":
        cles = [plan.x] + ([plan.series] if plan.series else [])
        if df.duplicated(subset=cles).any():
            if not plan.agregation:
                raise SpecInvalide("Plusieurs valeurs par %s : precise aggregation." % " et ".join(cles))
            plan._agregation_permise(plan.y)
            df = df.groupby(cles, as_index=False)[plan.y].agg(FONCTIONS[plan.agregation])
        xs = sorted(df[plan.x].dropna().unique())
        series = []
        groupes = [(None, df)] if not plan.series else list(df.groupby(plan.series))
        if len(groupes) > MAX_SERIES:
            raise SpecInvalide("%d series : %d au plus (filtre la colonne %s)."
                               % (len(groupes), MAX_SERIES, plan.series))
        for nom, g in groupes:
            par_x = g.set_index(plan.x)[plan.y]
            series.append({"nom": str(nom) if nom is not None else plan.libelle(plan.y),
                           "y": [_arrondi(par_x.get(x)) for x in xs]})
        sortie["spec"] = {"genre": "courbes", "donnees": {
            "x": [_arrondi(x, 2) for x in xs], "x_categoriel": plan.nature(plan.x) == "mois",
            "x_label": plan.libelle(plan.x), "y_label": plan.libelle(plan.y), "series": series,
            "ligne_zero": bool(df[plan.y].min() < 0 < df[plan.y].max())}}
        unite = plan.unite(plan.y)
        desc = "%s selon %s" % (plan.libelle(plan.y).capitalize(), plan.libelle(plan.x))
        resume["series"] = {s["nom"]: {"min": _arrondi(np.nanmin([v for v in s["y"] if v is not None] or [np.nan])),
                                       "max": _arrondi(np.nanmax([v for v in s["y"] if v is not None] or [np.nan]))}
                            for s in series}

    elif m == "nuage":
        paire = df[[c for c in (plan.label, plan.x, plan.y) if c]].dropna(subset=[plan.x, plan.y])
        if len(paire) < MIN_NUAGE:
            raise SpecInvalide("%d points : il en faut au moins %d pour un nuage interpretable."
                               % (len(paire), MIN_NUAGE))
        from scipy import stats
        r, p = stats.pearsonr(paire[plan.x], paire[plan.y])
        rho, _ = stats.spearmanr(paire[plan.x], paire[plan.y])
        etiquettes = paire[plan.label].astype(str) if plan.label else paire.index.astype(str)
        sortie["spec"] = {"genre": "nuage", "hauteur_pouces": 2.8, "donnees": {
            "points": [[e, _arrondi(a), _arrondi(b)] for e, a, b in
                       zip(etiquettes, paire[plan.x], paire[plan.y])],
            "x_label": "%s (%s)" % (plan.libelle(plan.x), plan.unite(plan.x)),
            "y_label": "%s (%s)" % (plan.libelle(plan.y), plan.unite(plan.y))}}
        unite = "%s ; %s" % (plan.unite(plan.x), plan.unite(plan.y))
        desc = "%s en fonction de %s" % (plan.libelle(plan.y).capitalize(), plan.libelle(plan.x))
        resume.update({"n": int(len(paire)), "pearson_r": _arrondi(r), "p_nominale": _arrondi(p, 4),
                       "spearman_rho": _arrondi(rho),
                       "lecture": "correlation simple, sans correction de tendance ni "
                                  "d'autocorrelation : description, pas preuve d'un lien"})
        notes["nuage"] = True

    elif m == "boites":
        groupes = [(str(k), g[plan.y].dropna()) for k, g in df.groupby(plan.group_by)]
        groupes = [(k, v) for k, v in groupes if len(v)]
        if len(groupes) > MAX_BOITES:
            raise SpecInvalide("%d groupes : %d au plus." % (len(groupes), MAX_BOITES))
        petits = [k for k, v in groupes if len(v) < MIN_BOITE]
        if petits:
            raise SpecInvalide("Groupes avec moins de %d valeurs (%s) : une boite n'y a pas de "
                               "sens ; filtre-les." % (MIN_BOITE, ", ".join(petits[:6])))
        sortie["spec"] = {"genre": "boites", "hauteur_pouces": 2.6, "donnees": {
            "groupes": [k for k, _ in groupes],
            "valeurs": [[_arrondi(x) for x in v] for _, v in groupes],
            "x_label": plan.libelle(plan.group_by), "y_label": plan.libelle(plan.y)}}
        unite = plan.unite(plan.y)
        desc = "Distribution de %s par %s" % (plan.libelle(plan.y), plan.libelle(plan.group_by))
        resume["medianes"] = {k: _arrondi(v.median()) for k, v in groupes}

    elif m == "carte":
        geo = plan.meta_jeu["geo"]
        valeurs = df[[geo["colonne"], geo["nom"], plan.y] + (["rang"] if "rang" in df else [])]
        valeurs = valeurs.dropna(subset=[plan.y])
        vmin, vmax = float(valeurs[plan.y].min()), float(valeurs[plan.y].max())
        if plan.nature(plan.y) == "rang" and plan.y != "rang":
            vmin, vmax = 0.0, 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
        cles_surligne = {normalise(s) for s in plan.surligne}
        zones = [{"pcode": r[geo["colonne"]], "nom": str(r[geo["nom"]]),
                  "rang": int(r["rang"]) if "rang" in r and pd.notna(r["rang"]) else None,
                  "valeur": _arrondi(r[plan.y])} for _, r in valeurs.iterrows()]
        tri = sorted(zones, key=lambda z: -(z["valeur"] or 0))
        sortie["spec"] = {"genre": "carte_zones", "donnees": {
            "niveau": geo["niveau"], "zones": zones, "vmin": vmin, "vmax": vmax,
            "legende": "%s (%s)" % (plan.libelle(plan.y), plan.unite(plan.y)),
            "surligne": [z["pcode"] for z in zones if normalise(z["nom"]) in cles_surligne],
            "etiquettes": [{"pcode": z["pcode"], "texte": str(i + 1)} for i, z in enumerate(tri[:5])],
            "etiquettes_encart": []}}
        unite = plan.unite(plan.y)
        desc = "%s par %s" % (plan.libelle(plan.y).capitalize(), geo["niveau"][:-1])
        resume["cinq_plus_fortes"] = {z["nom"]: z["valeur"] for z in tri[:5]}
        resume["zones_sans_valeur_hors_filtre"] = "les zones filtrees apparaissent en gris"

    elif m == "carte_chaleur":
        if df.duplicated(subset=[plan.series, plan.x]).any():
            raise SpecInvalide("Plusieurs valeurs par case : fixe les autres dimensions par des "
                               "filtres (ex. phase et metric).")
        pivot = df.pivot(index=plan.series, columns=plan.x, values=plan.y)
        sortie["spec"] = {"genre": "carte_chaleur", "hauteur_pouces": 0.24 * len(pivot) + 0.9,
                          "donnees": {"lignes": [str(i) for i in pivot.index],
                                      "colonnes": [str(int(c)) if float(c).is_integer() else str(c)
                                                   for c in pivot.columns],
                                      "valeurs": [[_arrondi(v) for v in ligne] for ligne in pivot.values],
                                      "vmax": 0.6, "titre_lignes": plan.libelle(plan.series),
                                      "titre_colonnes": plan.libelle(plan.x),
                                      "legende_couleur": plan.libelle(plan.y)}}
        unite = plan.unite(plan.y)
        desc = "%s par %s et %s" % (plan.libelle(plan.y).capitalize(), plan.libelle(plan.series),
                                    plan.libelle(plan.x))
        resume["extremes"] = {"min": _arrondi(np.nanmin(pivot.values)),
                              "max": _arrondi(np.nanmax(pivot.values))}

    else:  # tableau
        t = df[plan.colonnes_tableau]
        if plan.y and plan.y in df.columns:
            t = df.sort_values(plan.y, ascending=(plan.tri == "asc"))[plan.colonnes_tableau]
        t = t.head(plan.top or MAX_CATEGORIES)
        sortie = {"genre": "tableau", "colonnes": [plan.libelle(c) for c in plan.colonnes_tableau],
                  "lignes": [[_cellule(v) for v in ligne] for ligne in t.itertuples(index=False)]}
        unite = " ; ".join(sorted({plan.unite(c) for c in plan.colonnes_tableau
                                   if plan.nature(c) in NUMERIQUES})) or "sans objet"
        desc = "Extrait de %s" % plan.meta_jeu["description"].lower()
        resume["lignes_affichees"] = len(sortie["lignes"])

    legende = desc
    if plan.filtres:
        legende += " ; filtres : " + ", ".join(
            "%s %s %s" % (plan.libelle(c), op, v if not isinstance(v, list) else ", ".join(map(str, v)))
            for c, op, v in plan.filtres)
    if plan.top:
        legende += " ; %s premiers" % plan.top
    if "appariement" in notes:
        a = notes["appariement"]
        legende += " ; jointure avec %s : %d lignes appariées sur %d" % (
            plan.jointure["droite"], a["apparies"], a["total"])
        resume["appariement"] = a
    if notes.get("nuage"):
        legende += " ; corrélation simple, non corrigée de la tendance ni de l'autocorrélation"
    if provisoires:
        legende += " ; donnée provisoire : %s" % ", ".join(provisoires)
    legende += "."
    if plan.commentaire:
        legende += " " + plan.commentaire
    sortie.update({
        "titre": plan.titre or desc, "legende": legende, "unite": unite,
        "periode": _periode(plan, df), "source": plan.meta_jeu["source"], "resume": resume,
        "statut": "correle" if plan.jeu == "correlations" or notes.get("nuage") else "observe",
    })
    return sortie


def _cellule(v):
    if isinstance(v, float):
        if not np.isfinite(v):
            return "—"
        from .faits import nombre_fr
        return nombre_fr(v, 0 if v.is_integer() else 2).replace("-", "−")
    if isinstance(v, (int, np.integer)):
        from .faits import nombre_fr
        return nombre_fr(int(v), 0)
    return "—" if v is None else str(v)


def pour_rapport(brute):
    """(Figure ou Tableau d'origine 'a_la_demande', resume)."""
    from . import collecteurs
    r = executer(brute)
    if r["genre"] == "tableau":
        return collecteurs.tableau(r["colonnes"], r["lignes"], r["titre"], r["legende"],
                                   r["unite"], r["periode"], r["source"], r["statut"]), r["resume"]
    return collecteurs.figure(r["spec"], r["titre"], r["legende"], r["unite"], r["periode"],
                              r["source"], r["statut"], origine="a_la_demande"), r["resume"]
