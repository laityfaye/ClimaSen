"""Code et taches du projet (Phase 10): lecture, modification, execution.

Toutes les ECRITURES et EXECUTIONS passent par le protocole de jarvis/actions.py:
le modele depose une proposition, l'utilisateur l'approuve d'un clic, le
serveur execute. Ce module ne fait que le travail, sous des regles fixes:

LECTURE    tout le depot SAUF secrets, environnements, dossiers personnels,
           donnees brutes, fichiers binaires ou trop gros.
ECRITURE   scripts/, src/, tests/ uniquement, et quelques extensions texte.
           JAMAIS jarvis/ (Jarvis ne doit pas pouvoir reecrire ses propres
           protections, meme avec un clic d'approbation distrait), deploy/,
           .env, la configuration git ou les dependances.
EXECUTION  une liste fermee: les scripts du pipeline (ceux du module
           Pipeline du dashboard) et pytest sur un fichier de tests. Aucun
           argument libre, une seule tache a la fois, un delai maximal, un
           environnement sans les secrets du service.

Pourquoi pas une branche git dediee (envisagee au plan): le dossier de
travail porte souvent des changements non commites. Une branche partirait du
dernier commit et Jarvis modifierait une AUTRE version des fichiers que celle
que l'utilisateur a sous les yeux. D'ou une ecriture en place, encadree:
empreinte du fichier verifiee (rien n'a change depuis la proposition),
compilation Python avant ecriture, sauvegarde horodatee, ecriture atomique,
et annulation d'un clic.
"""
import difflib
import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("jarvis.code")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DOSSIER_JARVIS = PROJECT_DIR / ".jarvis"
SAUVEGARDES = DOSSIER_JARVIS / "sauvegardes"

EXTENSIONS_TEXTE = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
                    ".cfg", ".ini", ".html", ".css", ".js", ".ts", ".sh",
                    ".bat", ".service", ".conf", ".location", ".csv", ".sql"}
EXTENSIONS_ECRITURE = {".py", ".md", ".txt", ".json", ".yaml", ".yml",
                       ".toml", ".csv", ".css", ".html"}

# Dossiers (premier ou n-ieme composant du chemin) jamais lus.
DOSSIERS_INTERDITS = {".git", ".jarvis", "venv", ".venv", "env", "node_modules",
                      "__pycache__", "JARVIS-pro", "LINUX", ".pytest_cache",
                      ".mypy_cache", ".idea", ".vscode"}
# Motifs de nom de fichier jamais lus: secrets et equivalents.
NOMS_INTERDITS = re.compile(
    r"(^\.env|\.pem$|\.key$|\.p12$|\.pfx$|^id_rsa|credentials|secret|token|"
    r"password|\.kdbx$)", re.IGNORECASE)
PREFIXES_LECTURE_INTERDITS = ("data/raw/",)

RACINES_ECRITURE = ("scripts/", "src/", "tests/")
FICHIERS_ECRITURE_INTERDITS = {
    # Pont entre le dashboard et Jarvis: il decide de ce qui part vers le
    # modele (contexte de page). Il releve de la securite de Jarvis.
    "scripts/jarvis_widget.py",
}

MAX_LECTURE_OCTETS = 1_000_000
MAX_LIGNES_LUES = 400
# Le registre plafonne un resultat d'outil a 6000 caracteres et, faute de
# liste a raccourcir, couperait le JSON en plein milieu: la lecture s'arrete
# donc d'elle-meme sous ce budget et indique ou reprendre.
MAX_CARACTERES_LUS = 4500
MAX_CONTENU_ECRIT = 300_000
MAX_RESULTATS_RECHERCHE = 40
# Au-dela, la modification est REFUSEE, pas tronquee. Phase 12: un diff
# tronque a l'affichage laissait approuver du code jamais vu (une charge
# placee apres la 400e ligne d'un fichier cree n'apparaissait pas).
MAX_LIGNES_DIFF = 400


class RefusCode(Exception):
    """Chemin, contenu ou tache refuses. Le message part vers le modele."""


# =============================================================================
# Chemins
# =============================================================================
def _relatif(chemin_brut: str) -> str:
    """Chemin relatif normalise ('scripts/x.py'), ou RefusCode.

    Le chemin vient du MODELE: il est resolu puis compare a la racine du
    depot, ce qui neutralise '..', les chemins absolus et les liens
    symboliques qui pointeraient ailleurs.
    """
    if not chemin_brut or not str(chemin_brut).strip():
        raise RefusCode("Chemin vide.")
    brut = str(chemin_brut).strip().replace("\\", "/").lstrip("/")
    cible = (PROJECT_DIR / brut).resolve()
    try:
        rel = cible.relative_to(PROJECT_DIR.resolve())
    except ValueError:
        raise RefusCode("Chemin hors du projet: %s" % chemin_brut)
    return rel.as_posix()


def _verifier_lecture(rel: str) -> Path:
    parties = rel.split("/")
    if any(p in DOSSIERS_INTERDITS for p in parties):
        raise RefusCode("Dossier non consultable: %s" % rel)
    if NOMS_INTERDITS.search(parties[-1]):
        raise RefusCode("Fichier non consultable (secret possible): %s" % rel)
    if (rel + "/").startswith(PREFIXES_LECTURE_INTERDITS):
        raise RefusCode("Donnees brutes non consultables: %s" % rel)
    return PROJECT_DIR / rel


def _verifier_ecriture(rel: str) -> Path:
    chemin = _verifier_lecture(rel)
    if not rel.startswith(RACINES_ECRITURE):
        raise RefusCode(
            "Ecriture refusee: seuls scripts/, src/ et tests/ sont modifiables "
            "(demande: %s)." % rel)
    if rel in FICHIERS_ECRITURE_INTERDITS:
        raise RefusCode("Ce fichier releve de la securite d'Iris et n'est "
                        "pas modifiable par Iris: %s" % rel)
    if chemin.suffix.lower() not in EXTENSIONS_ECRITURE:
        raise RefusCode("Type de fichier non modifiable: %s" % chemin.suffix)
    return chemin


def empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _lire_texte(chemin: Path) -> str:
    if chemin.stat().st_size > MAX_LECTURE_OCTETS:
        raise RefusCode("Fichier trop volumineux (%d octets)." % chemin.stat().st_size)
    if chemin.suffix.lower() not in EXTENSIONS_TEXTE:
        raise RefusCode("Fichier non textuel: %s" % chemin.name)
    try:
        return chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise RefusCode("Fichier non lisible en UTF-8: %s" % chemin.name)


# =============================================================================
# Lecture
# =============================================================================
def lister(dossier: str = "") -> dict:
    rel = _relatif(dossier) if dossier else ""
    base = _verifier_lecture(rel) if rel else PROJECT_DIR
    if not base.is_dir():
        raise RefusCode("Dossier introuvable: %s" % (rel or "."))
    entrees = []
    for enfant in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        nom_rel = (Path(rel) / enfant.name).as_posix() if rel else enfant.name
        try:
            _verifier_lecture(nom_rel)
        except RefusCode:
            continue
        if enfant.is_dir():
            entrees.append({"nom": enfant.name + "/", "type": "dossier"})
        elif enfant.suffix.lower() in EXTENSIONS_TEXTE:
            entrees.append({"nom": enfant.name, "type": "fichier",
                            "octets": enfant.stat().st_size})
        if len(entrees) >= 200:
            break
    return {"dossier": rel or ".", "entrees": entrees,
            "modifiable_par_jarvis": bool(rel) and (rel + "/").startswith(RACINES_ECRITURE)}


def lire(fichier: str, debut: int = 1, fin: int = None) -> dict:
    rel = _relatif(fichier)
    chemin = _verifier_lecture(rel)
    if not chemin.is_file():
        raise RefusCode("Fichier introuvable: %s" % rel)
    lignes = _lire_texte(chemin).splitlines()
    debut = max(1, int(debut or 1))
    fin = min(len(lignes), int(fin) if fin else debut + MAX_LIGNES_LUES - 1)
    fin = min(fin, debut + MAX_LIGNES_LUES - 1)
    morceaux, taille = [], 0
    for i in range(debut, fin + 1):
        ligne = "%5d  %s" % (i, lignes[i - 1][:400])
        if morceaux and taille + len(ligne) > MAX_CARACTERES_LUS:
            fin = i - 1
            break
        morceaux.append(ligne)
        taille += len(ligne) + 1
    extrait = "\n".join(morceaux)
    modifiable = True
    try:
        _verifier_ecriture(rel)
    except RefusCode:
        modifiable = False
    return {"fichier": rel, "lignes_totales": len(lignes), "debut": debut,
            "fin": fin, "modifiable_par_jarvis": modifiable, "contenu": extrait,
            "suite": fin < len(lignes)}


def chercher(motif: str, dossier: str = "") -> dict:
    if not motif or len(motif) > 200:
        raise RefusCode("Motif vide ou trop long (200 caracteres maximum).")
    # Recherche LITTERALE, insensible a la casse. Phase 12: une expression
    # reguliere fournie par le modele comme "(a+)+$" figeait tout le serveur,
    # le moteur re gardant le verrou global de Python meme dans un thread.
    expression = re.compile(re.escape(motif), re.IGNORECASE)
    rel_base = _relatif(dossier) if dossier else ""
    base = _verifier_lecture(rel_base) if rel_base else PROJECT_DIR
    resultats, fichiers_lus = [], 0
    for racine, dossiers, fichiers in os.walk(base):
        dossiers[:] = sorted(d for d in dossiers if d not in DOSSIERS_INTERDITS)
        for nom in sorted(fichiers):
            chemin = Path(racine) / nom
            rel = chemin.relative_to(PROJECT_DIR).as_posix()
            try:
                _verifier_lecture(rel)
                if chemin.suffix.lower() not in EXTENSIONS_TEXTE or \
                        chemin.suffix.lower() == ".csv" or \
                        chemin.stat().st_size > MAX_LECTURE_OCTETS:
                    continue
                texte = chemin.read_text(encoding="utf-8")
            except (RefusCode, OSError, UnicodeDecodeError):
                continue
            fichiers_lus += 1
            for numero, ligne in enumerate(texte.splitlines(), 1):
                if expression.search(ligne[:2000]):
                    resultats.append({"fichier": rel, "ligne": numero,
                                      "texte": ligne.strip()[:200]})
                    if len(resultats) >= MAX_RESULTATS_RECHERCHE:
                        return {"motif": motif, "resultats": resultats,
                                "tronque": True, "fichiers_lus": fichiers_lus}
    return {"motif": motif, "resultats": resultats, "tronque": False,
            "fichiers_lus": fichiers_lus}


# =============================================================================
# Modification: preparation (outil) puis application (approbation)
# =============================================================================
def _verifier_syntaxe(rel: str, contenu: str) -> None:
    if not rel.endswith(".py"):
        return
    try:
        compile(contenu, rel, "exec")
    except SyntaxError as exc:
        raise RefusCode("Le code propose ne compile pas: %s (ligne %s)."
                        % (exc.msg, exc.lineno))


def _diff(rel: str, avant: str, apres: str) -> dict:
    lignes = list(difflib.unified_diff(avant.splitlines(), apres.splitlines(),
                                       "a/" + rel, "b/" + rel, lineterm="", n=2))
    ajoutees = sum(1 for l in lignes if l.startswith("+") and not l.startswith("+++"))
    retirees = sum(1 for l in lignes if l.startswith("-") and not l.startswith("---"))
    if len(lignes) > MAX_LIGNES_DIFF:
        raise RefusCode("Modification trop longue pour etre relue d'un coup "
                        "(%d lignes de diff, %d au plus): la decouper en "
                        "plusieurs propositions." % (len(lignes), MAX_LIGNES_DIFF))
    return {"diff": "\n".join(lignes), "diff_tronque": False,
            "lignes_ajoutees": ajoutees, "lignes_retirees": retirees}


def preparer_modification(fichier: str, ancien: str, nouveau: str,
                          toutes: bool = False) -> dict:
    """Calcule la modification SANS rien ecrire.

    ancien vide + fichier absent = creation. Sinon ancien doit apparaitre
    exactement une fois (ou toutes=True): un remplacement ambigu toucherait
    peut-etre une autre occurrence que celle visee.
    """
    rel = _relatif(fichier)
    chemin = _verifier_ecriture(rel)
    if nouveau is None:
        raise RefusCode("Le nouveau texte est requis.")
    if chemin.exists():
        if not chemin.is_file():
            raise RefusCode("Ce chemin est un dossier: %s" % rel)
        if not ancien:
            raise RefusCode("Le fichier existe deja: fournir le texte a remplacer.")
        avant = _lire_texte(chemin)
        n = avant.count(ancien)
        if n == 0:
            raise RefusCode("Texte a remplacer introuvable dans %s. Relire le "
                            "fichier: il a pu changer." % rel)
        if n > 1 and not toutes:
            raise RefusCode("Texte present %d fois dans %s: l'allonger pour le "
                            "rendre unique, ou demander toutes les occurrences."
                            % (n, rel))
        apres = avant.replace(ancien, nouveau) if toutes else avant.replace(ancien, nouveau, 1)
        mode = "remplacement"
    else:
        if ancien:
            raise RefusCode("Fichier introuvable: %s" % rel)
        if not chemin.parent.is_dir():
            raise RefusCode("Dossier parent introuvable: %s" % chemin.parent.name)
        avant, apres, n, mode = "", nouveau, 0, "creation"
    if apres == avant:
        raise RefusCode("La modification ne change rien.")
    if len(apres) > MAX_CONTENU_ECRIT:
        raise RefusCode("Fichier resultant trop volumineux.")
    _verifier_syntaxe(rel, apres)
    return {"fichier": rel, "mode": mode, "occurrences": n,
            "empreinte_avant": empreinte(avant) if chemin.exists() else None,
            "contenu": apres, **_diff(rel, avant, apres)}


def _ecrire_atomique(chemin: Path, contenu: str) -> None:
    temporaire = chemin.with_name(chemin.name + ".jarvis-tmp")
    temporaire.write_text(contenu, encoding="utf-8", newline="")
    os.replace(temporaire, chemin)


def appliquer_modification(payload: dict) -> dict:
    """Ecrit la modification approuvee. Revalide tout: la proposition a pu
    attendre, le fichier a pu changer entre-temps."""
    rel = payload["fichier"]
    chemin = _verifier_ecriture(rel)
    contenu = payload["contenu"]
    _verifier_syntaxe(rel, contenu)

    sauvegarde = None
    if payload.get("empreinte_avant") is None:
        if chemin.exists():
            raise RefusCode("Le fichier a ete cree entre-temps: proposition perimee.")
    else:
        if not chemin.exists():
            raise RefusCode("Le fichier a disparu depuis la proposition.")
        actuel = chemin.read_text(encoding="utf-8")
        if empreinte(actuel) != payload["empreinte_avant"]:
            raise RefusCode("Le fichier a change depuis la proposition: rien "
                            "n'a ete ecrit. Redemander a Iris.")
        horodatage = time.strftime("%Y%m%d-%H%M%S")
        sauvegarde = SAUVEGARDES / ("%s.%s.bak" % (rel.replace("/", "__"), horodatage))
        sauvegarde.parent.mkdir(parents=True, exist_ok=True)
        sauvegarde.write_text(actuel, encoding="utf-8", newline="")
    _ecrire_atomique(chemin, contenu)
    log.info("Fichier modifie par Jarvis: %s", rel)
    return {"fichier": rel, "mode": payload.get("mode"),
            "sauvegarde": sauvegarde.relative_to(PROJECT_DIR).as_posix() if sauvegarde else None,
            "empreinte_apres": empreinte(contenu),
            "lignes_ajoutees": payload.get("lignes_ajoutees"),
            "lignes_retirees": payload.get("lignes_retirees")}


def annuler_modification(resultat: dict) -> dict:
    """Retablit l'etat d'avant, si personne n'a retouche le fichier depuis."""
    rel = resultat["fichier"]
    chemin = _verifier_ecriture(rel)
    if not chemin.exists():
        raise RefusCode("Le fichier n'existe plus.")
    actuel = chemin.read_text(encoding="utf-8")
    if empreinte(actuel) != resultat["empreinte_apres"]:
        raise RefusCode("Le fichier a ete modifie depuis: annulation refusee "
                        "pour ne pas ecraser ce travail. La sauvegarde reste "
                        "disponible: %s" % resultat.get("sauvegarde"))
    if resultat.get("sauvegarde"):
        ancien = (PROJECT_DIR / resultat["sauvegarde"]).read_text(encoding="utf-8")
        _ecrire_atomique(chemin, ancien)
    else:
        chemin.unlink()           # c'etait une creation
    log.info("Modification annulee: %s", rel)
    return {"fichier": rel, "retabli": True}


# =============================================================================
# Execution de taches
# =============================================================================
TESTS_AUTORISES = re.compile(r"^tests/test_[A-Za-z0-9_]+\.py$")

# Scripts hors page Pipeline que Laity a ouverts a Iris (09/10/2026). Toujours
# soumis a approbation. Exclus : dashboard et utilitaires, 18 (banc d'epreuve :
# appels API payants), telechargements bruts CHIRPS/OISST (dizaines de Go),
# scripts d'archive (04 legacy, 11b, exports).
SCRIPTS_SUPPLEMENTAIRES = {
    "15_build_jarvis_index.py": "Index documentaire d'Iris (memoire + article)",
    "16_build_jarvis_fond_carte.py": "Fond de carte embarque d'Iris",
    "17_build_jarvis_sst_evenements.py": "Archive SST des evenements (animations)",
    "23_build_jarvis_fond_hud.py": "Fond d'ecran de l'interface I.R.I.S",
    "24_clustering_saisonnier.py": "Clustering saisonnier (analyse de controle)",
    "25_masque_senegal.py": "Effet du masque Senegal sur la detection",
    "26_indice_risque_departements.py": "Indice de risque par departement",
    "27_indice_risque_arrondissements.py": "Indice de risque par arrondissement",
    "28_contours_simplifies.py": "Contours simplifies (page Vulnerabilite)",
    "29_robustesse_indice.py": "Robustesse et validation de l'indice",
    "30_controle_transcriptions_ansd.py": "Controle des tableaux ANSD transcrits",
    "31_modulation_saisonniere_alea.py": "Modulation saisonniere de l'alea (etude)",
    "32_manifest_donnees.py": "Manifeste des donnees et figures de reference",
    "33_population_touchee_evenements.py": "Habitants des zones touchees par evenement",
    "34_communes_reconstruites.py": "Communes reconstruites (contours approximatifs)",
    "35_telecharger_odp_ansd.py": "Telechargement des donnees de l'ANSD (API SDMX)",
    "36_correspondance_zones_ansd.py": "Correspondance des codes de zone ANSD / ClimatSen",
    "37_exposition_projetee.py": "Exposition projetee 2026 et 2030",
    "38_synchroniser_ansd.py": "Synchronisation avec l'API de l'ANSD",
    "39_verifier_sources.py": "Verification des donnees sources contre la reference",
    "40_saisons_recentes.py": "Saisons recentes (2024 et apres)",
}

# Options acceptees, script par script : LISTE FERMEE, valeurs numeriques ou
# drapeaux seulement (aucun chemin, aucun texte libre). Forme d'une regle :
#   ("drapeau",)                              option sans valeur
#   (type, n_min, n_max, v_min, v_max)        type "entier" ou "reel"
_ANNEE = (1981, 2035)
OPTIONS_SCRIPTS = {
    "04_teleconnections_analysis.py": {
        "--no-by-phase": ("drapeau",),
        "--lags": ("entier", 1, 13, 0, 12)},
    "11_kmeans_sst_analysis.py": {
        "--by-phase": ("drapeau",), "--global": ("drapeau",),
        "--k-phase1": ("entier", 1, 1, 2, 15), "--k-phase2": ("entier", 1, 1, 2, 15),
        "--k-phase3": ("entier", 1, 1, 2, 15), "--k-all": ("entier", 1, 1, 2, 15)},
    "extract_daily_indices_from_sst.py": {"--years": ("entier", 2, 2) + _ANNEE},
    "15_build_jarvis_index.py": {"--inspecter": ("drapeau",)},
    "17_build_jarvis_sst_evenements.py": {"--par-phase": ("entier", 1, 1, 1, 100)},
    "19_build_sst_cube.py": {"--annees": ("entier", 1, 60) + _ANNEE,
                             "--telecharger": ("drapeau",)},
    "20_veille_presaison.py": {
        "--annee": ("entier", 1, 1) + _ANNEE, "--retro": ("entier", 2, 2) + _ANNEE,
        "--partiel": ("drapeau",), "--sans-c3s": ("drapeau",), "--kit": ("drapeau",),
        "--competence": ("drapeau",), "--familles": ("drapeau",)},
    "22_veille_mensuelle.py": {"--sans-telechargement": ("drapeau",)},
    "27_indice_risque_arrondissements.py": {"--osm": ("drapeau",)},
    "28_contours_simplifies.py": {"--tolerance": ("reel", 1, 1, 0.0001, 0.05)},
    "39_verifier_sources.py": {"--ecrire-reference": ("drapeau",),
                               "--rapide": ("drapeau",)},
    "40_saisons_recentes.py": {"--annee-debut": ("entier", 1, 1, 2024, 2035)},
}


def scripts_autorises() -> dict:
    """Scripts executables: {nom: libelle}. Ceux du module Pipeline du
    dashboard, plus SCRIPTS_SUPPLEMENTAIRES (le libelle du Pipeline l'emporte)."""
    try:
        from .tools.dataset import get
        etapes = get("pipeline")["steps"]
    except Exception:          # pragma: no cover - depend de l'installation
        etapes = []
    autorises = dict(SCRIPTS_SUPPLEMENTAIRES)
    autorises.update({e["script"]: e["label"] for e in etapes})
    return autorises


def options_texte(script: str) -> str:
    """Options acceptees par un script, lisibles (description d'outil, refus)."""
    regles = OPTIONS_SCRIPTS.get(script) or {}
    morceaux = []
    for nom, regle in regles.items():
        if regle[0] == "drapeau":
            morceaux.append(nom)
        else:
            n = str(regle[1]) if regle[1] == regle[2] else "%d-%d" % regle[1:3]
            morceaux.append("%s (%s %s, %s..%s)" % (nom, n, regle[0], regle[3], regle[4]))
    return ", ".join(morceaux) or "aucune"


def valider_options(script: str, options) -> tuple:
    """Controle les options demandees contre OPTIONS_SCRIPTS.

    Retourne (arguments de la ligne de commande, options normalisees). Les
    options normalisees sont ce qu'on stocke dans la proposition ; elles sont
    RE-validees a l'approbation, rien du modele n'arrive tel quel a la commande.
    """
    if not options:
        return [], {}
    if not isinstance(options, dict):
        raise RefusCode("options doit etre un objet {option: valeur}.")
    regles = OPTIONS_SCRIPTS.get(script) or {}
    argv, propres = [], {}
    for nom_brut, valeur in options.items():
        nom = "--" + str(nom_brut).lstrip("-")
        regle = regles.get(nom)
        if regle is None:
            raise RefusCode("Option non autorisee pour %s: %r. Options acceptees: %s."
                            % (script, nom_brut, options_texte(script)))
        if regle[0] == "drapeau":
            if valeur is True:
                argv.append(nom)
                propres[nom] = True
            elif valeur is not False and valeur is not None:
                raise RefusCode("%s est un drapeau: valeur true ou false." % nom)
            continue
        type_, n_min, n_max, v_min, v_max = regle
        valeurs = valeur if isinstance(valeur, list) else [valeur]
        if not n_min <= len(valeurs) <= n_max:
            raise RefusCode("%s attend %s valeur(s)." % (
                nom, n_min if n_min == n_max else "%d a %d" % (n_min, n_max)))
        nettes = []
        for v in valeurs:
            correct = (isinstance(v, int) if type_ == "entier"
                       else isinstance(v, (int, float))) and not isinstance(v, bool)
            if not correct or not v_min <= v <= v_max:
                raise RefusCode("%s: valeur %r refusee (%s entre %s et %s)."
                                % (nom, v, type_, v_min, v_max))
            nettes.append(v)
        argv.append(nom)
        argv.extend(str(v) for v in nettes)
        propres[nom] = nettes if n_max > 1 else nettes[0]
    return argv, propres


def preparer_tache(script: str, cible_tests: str = None, options=None) -> dict:
    if script == "pytest":
        if options:
            raise RefusCode("pytest n'accepte pas d'options (seulement test_file).")
        if cible_tests:
            rel = _relatif(cible_tests)
            if not TESTS_AUTORISES.match(rel) or not (PROJECT_DIR / rel).is_file():
                raise RefusCode("Fichier de tests introuvable ou non autorise: %s "
                                "(attendu: tests/test_xxx.py)." % cible_tests)
            commande = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", rel]
        else:
            rel = "tests/"
            commande = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/"]
        return {"script": "pytest", "cible": rel, "libelle": "Tests (%s)" % rel,
                "commande": commande}
    autorises = scripts_autorises()
    if script not in autorises:
        raise RefusCode("Script non autorise: %r. Valeurs acceptees: pytest, %s."
                        % (script, ", ".join(sorted(autorises))))
    argv, propres = valider_options(script, options)
    return {"script": script, "cible": "scripts/" + script,
            "libelle": autorises[script],
            "options": propres, "arguments": " ".join(argv),
            "commande": [sys.executable, "scripts/" + script] + argv}


def _environnement() -> dict:
    """Environnement du sous-processus, SANS les secrets du service."""
    env = {}
    for cle, valeur in os.environ.items():
        if re.search(r"(ANTHROPIC|JARVIS|SECRET|TOKEN|PASSWORD|API_KEY)", cle, re.I):
            continue
        env[cle] = valeur
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = "Agg"
    return env


NOMS_SECRETS = re.compile(r"(ANTHROPIC|SECRET|TOKEN|PASSWORD|API_KEY|HASH)", re.I)
MOTIFS_SECRETS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|pwd)"
               r"[\"']?\s*[=:]\s*[\"']?)([^\s\"',]{6,})"),
    re.compile(r"\$scrypt\$[^\s\"']+"),
]


def secrets_connus(extra=()) -> list:
    """Valeurs a ne jamais laisser sortir d'une tache: variables sensibles
    de l'environnement du service ET du fichier .env (qu'un script pourrait
    lire lui-meme), plus celles que fournit l'appelant."""
    valeurs = set(v for v in extra if v and len(v) >= 8)
    for cle, valeur in os.environ.items():
        if NOMS_SECRETS.search(cle) and valeur and len(valeur) >= 8:
            valeurs.add(valeur)
    env = PROJECT_DIR / ".env"
    try:
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                cle, valeur = ligne.split("=", 1)
                valeur = valeur.strip().strip("\"'")
                if NOMS_SECRETS.search(cle) and len(valeur) >= 8:
                    valeurs.add(valeur)
    except OSError:
        pass
    return sorted(valeurs, key=len, reverse=True)


def masquer(texte: str, secrets=()) -> str:
    """Remplace tout secret connu, et tout ce qui en a la forme."""
    for valeur in secrets:
        texte = texte.replace(valeur, "[SECRET MASQUE]")
    texte = MOTIFS_SECRETS[0].sub("[SECRET MASQUE]", texte)
    texte = MOTIFS_SECRETS[1].sub(lambda m: m.group(1) + "[SECRET MASQUE]", texte)
    texte = MOTIFS_SECRETS[2].sub("[SECRET MASQUE]", texte)
    return texte


class Taches:
    """Une seule tache a la fois: les scripts du pipeline sont lourds, et
    deux executions concurrentes ecriraient les memes fichiers.

    La sortie d'une tache repart vers l'interface ET vers le modele
    (get_task_status): les secrets y sont masques. Phase 12: sans cela, un
    script qui lisait le .env et l'affichait faisait sortir la cle API."""

    def __init__(self, secrets=()):
        self._verrou = threading.Lock()
        self.en_cours = None
        self._secrets_extra = tuple(secrets)

    def occupe(self) -> bool:
        return self.en_cours is not None

    def lancer(self, commande: list, delai: int, quand_fini) -> None:
        with self._verrou:
            if self.en_cours is not None:
                raise RefusCode("Une tache est deja en cours (%s). Attendre sa fin."
                                % self.en_cours)
            self.en_cours = " ".join(commande[1:])[:120]

        def travail():
            debut = time.time()
            try:
                proc = subprocess.run(commande, cwd=str(PROJECT_DIR),
                                      env=_environnement(), capture_output=True,
                                      text=True, encoding="utf-8",
                                      errors="replace", timeout=delai)
                resultat = {"code_retour": proc.returncode,
                            "reussi": proc.returncode == 0,
                            "sortie_fin": _fin(proc.stdout, proc.stderr)}
            except subprocess.TimeoutExpired as exc:
                resultat = {"code_retour": None, "reussi": False,
                            "erreur": "Delai depasse (%d s): tache interrompue." % delai,
                            "sortie_fin": _fin(exc.stdout or "", exc.stderr or "")}
            except Exception as exc:  # pragma: no cover - defensif
                resultat = {"code_retour": None, "reussi": False, "erreur": str(exc)}
            if resultat.get("sortie_fin"):
                resultat["sortie_fin"] = masquer(resultat["sortie_fin"],
                                                 secrets_connus(self._secrets_extra))
            resultat["duree_s"] = round(time.time() - debut, 1)
            with self._verrou:
                self.en_cours = None
            quand_fini(resultat)

        threading.Thread(target=travail, name="jarvis-tache", daemon=True).start()


def _fin(stdout, stderr, n=40) -> str:
    def texte(v):
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else (v or "")
    lignes = (texte(stdout) + ("\n" + texte(stderr) if stderr else "")).splitlines()
    return "\n".join(l[:300] for l in lignes[-n:])
