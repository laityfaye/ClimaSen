"""Fiche d'une demande de rapport, et la regle de la question unique.

Le modele remplit des champs (type, zone, periode, phase, saison, public) a
partir du langage naturel; ce module les VALIDE et les COMPLETE:

  - la zone passe par le gazetteer: plusieurs candidats = ambiguite;
  - "l'hivernage prochain" est calcule a partir de la date du jour, jamais
    devine par le modele;
  - les periodes sont bornees a la couverture des donnees (1981-2023).

Regle de la question unique: si un champ obligatoire manque ou est ambigu,
on renvoie UNE question, sur le premier champ dans l'ordre
type > zone > periode > saison. La session est notee: a l'appel suivant, plus
aucune question n'est posee, les valeurs par defaut s'appliquent et sont
ecrites dans le rapport ("Hypotheses retenues"). Le compteur est tenu cote
serveur: le modele ne peut pas poser une seconde question par ce canal.
"""
import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from ..tools.common import (METRIQUES, ToolInputError, champ_entier, champ_enum,
                            champ_texte, normalise, resoudre_phase)
from . import HORIZONS, LIBELLES_TYPE, PUBLICS, TYPES
from .gazetteer import PAYS, Lieu

PREMIERE_ANNEE = 1981
DERNIERE_ANNEE = 2023
PREMIERE_ANNEE_SST = 1983
MAX_FIGURES_SUPPLEMENTAIRES = 3
MAX_FIGURES_REFERENCE = 3

_ALIAS_TYPES = {
    "historique": "historique", "historiques": "historique", "evenements": "historique",
    "bilan": "historique", "extremes": "historique", "passe": "historique",
    "teleconnexions": "teleconnexions", "teleconnexion": "teleconnexions",
    "correlations": "teleconnexions", "sst": "teleconnexions", "ocean": "teleconnexions",
    "vulnerabilite": "vulnerabilite", "risque": "vulnerabilite", "indicederisque": "vulnerabilite",
    "vulnerabilitecommunale": "vulnerabilite", "communal": "vulnerabilite",
    "veille": "veille", "bulletin": "veille", "presaison": "veille",
    "bulletindeveille": "veille", "veillepresaison": "veille", "saison": "veille",
}


def saison_visee(horizon: str, aujourd_hui: dt.date) -> int:
    """Saison des pluies (mai-octobre) visee par "prochaine" ou "en cours".

    En octobre 2026, la saison 2026 s'acheve: "l'hivernage prochain" est 2027.
    En mars 2026, il n'a pas commence: "prochain" est 2026.
    """
    if horizon == "en_cours":
        if 5 <= aujourd_hui.month <= 10:
            return aujourd_hui.year
        return aujourd_hui.year + (1 if aujourd_hui.month > 10 else 0)
    return aujourd_hui.year if aujourd_hui.month < 5 else aujourd_hui.year + 1


@dataclass
class ReportSpec:
    type: str
    lieu: Lieu
    annee_debut: int
    annee_fin: int
    phase: str
    saison: Optional[int]
    metrique: str
    public: str
    hypotheses: List[str] = field(default_factory=list)
    demande: str = ""
    figures_reference: List[str] = field(default_factory=list)
    figures_supplementaires: List[dict] = field(default_factory=list)

    def cle(self) -> dict:
        """Ce qui determine le contenu (cache): pas les hypotheses ni la demande."""
        return {"type": self.type, "zone": self.lieu.code, "debut": self.annee_debut,
                "fin": self.annee_fin, "phase": self.phase, "saison": self.saison,
                "metrique": self.metrique, "public": self.public,
                "figures_reference": list(self.figures_reference),
                "figures_supplementaires": list(self.figures_supplementaires)}

    def vue(self) -> dict:
        return {"type": self.type, "type_libelle": LIBELLES_TYPE[self.type],
                "zone": self.lieu.vue(), "periode": [self.annee_debut, self.annee_fin],
                "phase": self.phase, "saison": self.saison, "metrique": self.metrique,
                "public": self.public, "hypotheses": list(self.hypotheses)}


class EtatClarification:
    """Sessions auxquelles une question vient d'etre posee (une seule par demande)."""

    def __init__(self, ttl_seconds: int = 1800):
        self.ttl = ttl_seconds
        self._poses = {}
        self._verrou = threading.Lock()

    def deja_posee(self, session_id: str) -> bool:
        with self._verrou:
            t = self._poses.get(session_id)
            return t is not None and time.time() - t < self.ttl

    def noter(self, session_id: str) -> None:
        with self._verrou:
            self._poses[session_id] = time.time()

    def effacer(self, session_id: str) -> None:
        with self._verrou:
            self._poses.pop(session_id, None)

    def purger(self) -> None:
        limite = time.time() - self.ttl
        with self._verrou:
            for sid in [s for s, t in self._poses.items() if t < limite]:
                del self._poses[sid]


def _question(champ, question, options):
    return {"statut": "question", "champ": champ, "question": question,
            "options": options[:6],
            "consigne": ("Pose cette question a l'utilisateur telle quelle (une seule fois, sans "
                         "autre question), avec les options. Quand il repond, rappelle "
                         "generate_report avec les memes champs plus la 'valeur' de l'option "
                         "choisie. Ne lance rien d'autre en attendant.")}


def _type(params):
    brut = params.get("type")
    if brut is None:
        return None
    cle = normalise(brut)
    if cle in _ALIAS_TYPES:
        return _ALIAS_TYPES[cle]
    raise ToolInputError("type de rapport inconnu: %r. Valeurs acceptees: %s."
                         % (brut, ", ".join(TYPES)))


def _options_lieux(lieux):
    return [{"libelle": l.libelle(), "valeur": {"zone_code": l.code}} for l in lieux]


def preparer(params: dict, gazetteer, bulletins_disponibles=(), aujourd_hui=None,
             question_deja_posee=False) -> dict:
    """Valide et complete la demande.

    Renvoie {"statut": "pret", "spec": ReportSpec} ou {"statut": "question", ...}.
    Avec question_deja_posee=True, ne renvoie JAMAIS de question: les valeurs
    par defaut s'appliquent et deviennent des hypotheses ecrites.
    """
    aujourd_hui = aujourd_hui or dt.date.today()
    forcer = bool(question_deja_posee)
    hyp = []

    # --- type -------------------------------------------------------------
    type_ = _type(params)
    zone_texte = champ_texte(params, "zone", maxi=80)
    zone_code = champ_texte(params, "zone_code", maxi=80)
    if type_ is None:
        if not forcer:
            return _question("type", "Quel type de rapport souhaitez-vous ?", [
                {"libelle": LIBELLES_TYPE[t], "valeur": {"type": t}} for t in TYPES])
        type_ = "vulnerabilite" if (zone_texte or zone_code) else "historique"
        hyp.append("Type de rapport non précisé : %s retenu." % LIBELLES_TYPE[type_].lower())

    # --- zone -------------------------------------------------------------
    lieu = None
    if zone_code:
        lieu = gazetteer.par_code(zone_code) if zone_code != "SN" else PAYS
        if lieu is None:
            raise ToolInputError("zone_code inconnu: %r. Utilise la 'valeur' d'une option "
                                 "proposee, ou le champ zone (nom du lieu)." % zone_code)
    elif zone_texte:
        res = gazetteer.resoudre(zone_texte)
        if res.unique is not None:
            lieu = res.unique
            if not res.exact:
                hyp.append("Zone « %s » comprise comme : %s." % (zone_texte, lieu.libelle()))
        elif res.candidats:
            if not forcer:
                return _question(
                    "zone", "Plusieurs lieux correspondent à « %s ». Lequel visez-vous ?"
                    % zone_texte, _options_lieux(res.candidats))
            lieu = res.candidats[0]
            hyp.append("Zone « %s » ambiguë : %s retenu par défaut." % (zone_texte, lieu.libelle()))
        else:
            if not forcer:
                opts = [{"libelle": s, "valeur": {"zone": s}} for s in res.suggestions]
                opts.append({"libelle": "Ensemble du Sénégal", "valeur": {"zone_code": "SN"}})
                return _question(
                    "zone", "Je ne trouve pas « %s » parmi les régions, départements, "
                    "arrondissements et communes du Sénégal. Quelle zone visez-vous ?"
                    % zone_texte, opts)
            lieu = PAYS
            hyp.append("Zone « %s » introuvable dans les données : rapport établi pour "
                       "l'ensemble du Sénégal." % zone_texte)
    if lieu is None:
        if type_ == "vulnerabilite" and not forcer:
            return _question("zone", "Pour quelle zone voulez-vous le rapport de vulnérabilité ?", [
                {"libelle": "Ensemble du Sénégal (classement national)",
                 "valeur": {"zone_code": "SN"}},
                {"libelle": "Une région, un département, un arrondissement ou une commune "
                            "(préciser le nom)", "valeur": {"zone": "<nom du lieu>"}}])
        lieu = PAYS
        if type_ != "teleconnexions":
            hyp.append("Zone non précisée : rapport établi pour l'ensemble du Sénégal.")
    if type_ == "teleconnexions" and lieu.niveau != "pays":
        hyp.append("Les téléconnexions sont calculées à l'échelle du Sénégal : la zone « %s » "
                   "n'en modifie pas les résultats." % lieu.nom)
        lieu = PAYS

    # --- periode ----------------------------------------------------------
    debut = champ_entier(params, "year_min", mini=1800, maxi=2200)
    fin = champ_entier(params, "year_max", mini=1800, maxi=2200)
    premiere = PREMIERE_ANNEE_SST if type_ == "teleconnexions" else PREMIERE_ANNEE
    if type_ in ("historique",):
        if debut is not None and fin is not None and debut > fin:
            debut, fin = fin, debut
        d = debut if debut is not None else premiere
        f = fin if fin is not None else DERNIERE_ANNEE
        if f < premiere or d > DERNIERE_ANNEE:
            if not forcer:
                return _question("periode", "Les données de pluie couvrent %d-%d, et la période "
                                 "demandée (%d-%d) est en dehors. Quelle période retenir ?"
                                 % (premiere, DERNIERE_ANNEE, d, f), [
                                     {"libelle": "Toute la période %d-%d" % (premiere, DERNIERE_ANNEE),
                                      "valeur": {"year_min": premiere, "year_max": DERNIERE_ANNEE}},
                                     {"libelle": "Les dix dernières années disponibles (2014-2023)",
                                      "valeur": {"year_min": 2014, "year_max": 2023}}])
            d, f = premiere, DERNIERE_ANNEE
            hyp.append("Période demandée hors des données : période complète %d-%d retenue."
                       % (d, f))
        elif d < premiere or f > DERNIERE_ANNEE:
            hyp.append("Période ramenée à la couverture des données : %d-%d."
                       % (max(d, premiere), min(f, DERNIERE_ANNEE)))
            d, f = max(d, premiere), min(f, DERNIERE_ANNEE)
        if f - d + 1 < 10:
            hyp.append("Période courte (%d ans) : tendances et comparaisons peu robustes."
                       % (f - d + 1))
    else:
        d, f = premiere, DERNIERE_ANNEE
        if (debut is not None or fin is not None) and type_ == "teleconnexions":
            hyp.append("Les corrélations sont établies sur la période complète %d-%d ; la "
                       "période demandée n'est pas applicable à ce rapport." % (d, f))

    # --- phase -------------------------------------------------------------
    phase = "Toutes phases"
    if params.get("phase") is not None:
        phase = resoudre_phase(params["phase"])

    # --- saison (veille) ---------------------------------------------------
    saison = None
    if type_ == "veille":
        saison = champ_entier(params, "season", mini=1981, maxi=2100)
        horizon = champ_enum(params, "horizon", list(HORIZONS))
        if saison is None:
            saison = saison_visee(horizon or "prochaine", aujourd_hui)
            if horizon is None:
                hyp.append("Saison non précisée : saison %d (la prochaine saison des pluies à "
                           "la date du %s)." % (saison, aujourd_hui.strftime("%d/%m/%Y")))
        dispo = sorted(bulletins_disponibles, reverse=True)
        if dispo and saison not in dispo:
            if not forcer:
                return _question("saison", "Aucun bulletin de veille n'existe pour la saison %d. "
                                 "Lequel voulez-vous ?" % saison, [
                                     {"libelle": "Saison %d" % a, "valeur": {"season": a}}
                                     for a in dispo[:5]])
            proche = min(dispo, key=lambda a: abs(a - saison))
            hyp.append("Pas de bulletin pour %d : bulletin %d retenu." % (saison, proche))
            saison = proche

    # --- metrique et public --------------------------------------------------
    metrique = champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")
    public = champ_enum(params, "audience", list(PUBLICS))
    if public is None:
        public = "decideur"
        hyp.append("Public non précisé : version « décideurs » (protection civile, "
                   "collectivités).")

    # --- figures en plus ------------------------------------------------------
    refs = params.get("reference_figures") or []
    if not isinstance(refs, list) or len(refs) > MAX_FIGURES_REFERENCE:
        raise ToolInputError("reference_figures: liste de %d identifiants au plus."
                             % MAX_FIGURES_REFERENCE)
    supp = params.get("extra_figures") or []
    if not isinstance(supp, list) or len(supp) > MAX_FIGURES_SUPPLEMENTAIRES:
        raise ToolInputError("extra_figures: liste de %d specifications au plus."
                             % MAX_FIGURES_SUPPLEMENTAIRES)
    if any(not isinstance(s, dict) for s in supp):
        raise ToolInputError("extra_figures: chaque element est un objet (spec de figure).")

    spec = ReportSpec(type=type_, lieu=lieu, annee_debut=d, annee_fin=f, phase=phase,
                      saison=saison, metrique=metrique, public=public, hypotheses=hyp,
                      demande=champ_texte(params, "request", maxi=300) or "",
                      figures_reference=[str(r) for r in refs],
                      figures_supplementaires=supp)
    return {"statut": "pret", "spec": spec}

