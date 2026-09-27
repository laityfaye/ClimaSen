"""Production d'un bulletin: enchaine cube, projection, C3S et composition.

Regle d'or: le bulletin de l'annee N n'utilise QUE ce qui etait connu en
avril de l'annee N. Le modele de projection apprend sur les saisons < N,
la calibration C3S exclut N. Un bulletin retrospectif (N <= 2023) montre
donc exactement ce que le systeme aurait dit a l'epoque, et sa section
"verification" dit si c'etait juste.
"""
import datetime as dt
import json
import warnings

from . import DOSSIER_SORTIE
from . import annees as mod_annees
from . import bulletin as mod_bulletin
from . import c3s as mod_c3s
from . import projection as mod_proj
from .cube import Cube, CubeIndisponible

COMPETENCE = DOSSIER_SORTIE / "competence_projection.json"
MIN_MOIS_PARTIEL = 2


def _ecrire_json(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(chemin)


def _lire_json(chemin):
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else None


def competence_projection(ctx=None, recalculer=False, journal=print):
    """Competence du modele de projection (calcul long, mis en cache)."""
    if not recalculer:
        comp = _lire_json(COMPETENCE)
        if comp:
            return comp
    ctx = ctx or mod_proj.Contexte(Cube.charger())
    journal("Evaluation de la competence de la projection (plusieurs minutes)...")
    comp = mod_proj.evaluer(ctx, journal=journal)
    comp["calcule_le"] = dt.date.today().isoformat()
    comp["annees_etat"] = [ctx.annees_etat()[0], ctx.annees_etat()[-1]]
    _ecrire_json(COMPETENCE, comp)
    return comp


def calibration_c3s(annee_exclue=None, centre=mod_c3s.SYSTEME_DEFAUT, journal=print):
    """Calibration C3S (cache), recalculee sans l'annee du bulletin si besoin."""
    chemin = DOSSIER_SORTIE / ("calibration_c3s_%s.json" % centre)
    cal = _lire_json(chemin)
    if cal is None:
        cal = mod_c3s.calibration_complete(centre, journal=journal)
        cal["calcule_le"] = dt.date.today().isoformat()
        _ecrire_json(chemin, cal)
    if annee_exclue is not None and annee_exclue in cal["annees"]:
        _, annees = mod_c3s.SYSTEMES[centre]
        membres = {a: mod_c3s.lire(mod_c3s.fichier(a, centre)) for a in annees if a != annee_exclue}
        cal = dict(mod_c3s.calibrer(membres), centre=centre, systeme=mod_c3s.SYSTEMES[centre][0],
                   annee_exclue=int(annee_exclue))
    return cal


def _projection(ctx, annee, partiel, journal):
    """Projection nov-avr de l'annee: modele appris sur les saisons < annee."""
    manquants = ctx.cube.mois_etat_manquants(annee)
    disponibles = [m for m in ctx.cube.mois_etat(annee) if m not in manquants]
    if manquants and (not partiel or len(disponibles) < MIN_MOIS_PARTIEL):
        raise CubeIndisponible(
            "Etat novembre-avril incomplet pour %d: manque %s (dernier mois du cube: %s)." % (
                annee, ", ".join("%02d/%d" % (m, a) for a, m in manquants),
                "%02d/%d" % tuple(reversed(ctx.cube.dernier_mois()))))
    fin_obs = int(ctx.empreinte.index.max())
    app = [a for a in range(1983, min(annee - 1, fin_obs) + 1)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        modele = mod_proj.Modele(ctx, app)
        champ = ctx.etat(annee, partiel=bool(manquants))
        p = modele.probabilite(champ, annee)
        conf = mod_proj.ressemblance_memoire(ctx, champ, annee, modele)
        # Les clusters du memoire ont vu toutes les saisons: dans un bulletin
        # retrospectif, ne pas citer comme reference l'annee meme du bulletin.
        for c in conf:
            c["annees_principales"] = [a for a in c.get("annees_principales", []) if a < annee]
        ana = mod_proj.annees_analogues(ctx, champ, annee, modele, nombre=5, avant=annee)
    journal("  projection %d: p=%.2f, configuration la plus proche C%d" % (
        annee, p, conf[0]["configuration"]))
    return {
        "probabilite_experimentale": round(p, 3),
        "annees_apprentissage": [app[0], app[-1]],
        "configurations": conf[:3],
        "toutes_configurations": [{"configuration": c["configuration"], "correlation": c["correlation"]}
                                  for c in conf],
        "analogues": ana,
    }, disponibles, bool(manquants)


def produire(annee, avec_c3s=True, partiel=False, journal=print, ecrire=True):
    """Produit (et ecrit) le bulletin de l'annee. Ne leve pas pour une source absente."""
    avertissements = []
    empreinte = mod_annees.empreinte()
    projection = etat_mois = None
    etat_partiel = False
    comp = None
    try:
        ctx = mod_proj.Contexte(Cube.charger())
        comp = competence_projection(ctx, journal=journal)
        projection, mois, etat_partiel = _projection(ctx, annee, partiel, journal)
        etat_mois = mod_bulletin.mois_lisibles(mois)
        if etat_partiel:
            avertissements.append(
                "État océanique partiel (%s) : bulletin provisoire, à refaire fin avril."
                % ", ".join(etat_mois))
    except CubeIndisponible as exc:
        avertissements.append("Projection océanique indisponible : %s" % exc)

    c3s = {"disponible": False, "raison": "non demandée"}
    if avec_c3s:
        try:
            cal = calibration_c3s(annee_exclue=annee, journal=journal)
            prev = mod_c3s.prevision(annee, cal, journal=journal)
            c3s = dict(prev, disponible=True, competence=cal["competence"],
                       calibration_annees=[cal["annees"][0], cal["annees"][-1]])
            journal("  C3S %d: p=%.2f" % (annee, prev["probabilite_annee_extreme"]))
        except mod_c3s.C3SIndisponible as exc:
            c3s = {"disponible": False, "raison": str(exc)}
            avertissements.append("Prévision C3S indisponible : %s" % exc)

    fin_obs = int(empreinte.index.max())
    if annee > fin_obs + 1:
        avertissements.append(
            "Les saisons %d à %d ne sont pas encore dans le catalogue CHIRPS : le modèle "
            "n'apprend que jusqu'à %d." % (fin_obs + 1, annee - 1, fin_obs))

    b = mod_bulletin.composer(annee, projection=projection, c3s=c3s,
                              competence_projection=comp, empreinte=empreinte,
                              etat_mois=etat_mois, etat_partiel=etat_partiel,
                              avertissements=avertissements)
    if ecrire:
        _ecrire_json(DOSSIER_SORTIE / ("bulletin_%d.json" % annee), b)
        (DOSSIER_SORTIE / ("bulletin_%d.md" % annee)).write_text(
            mod_bulletin.markdown(b), encoding="utf-8")
        table, _ = mod_annees.classement(empreinte)
        table.to_csv(DOSSIER_SORTIE / "classement_annees.csv", encoding="utf-8")
    return b


def bulletins_disponibles():
    """Annees ayant un bulletin ecrit, plus recente en premier."""
    if not DOSSIER_SORTIE.is_dir():
        return []
    annees = []
    for f in DOSSIER_SORTIE.glob("bulletin_*.json"):
        try:
            annees.append(int(f.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(annees, reverse=True)


def lire_bulletin(annee):
    return _lire_json(DOSSIER_SORTIE / ("bulletin_%d.json" % int(annee)))
