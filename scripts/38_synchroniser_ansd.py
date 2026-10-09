#!/usr/bin/env python3
"""Synchronisation de ClimatSen avec l'API SDMX de l'ANSD (bouton « Synchroniser »).

Lancee depuis l'onglet « Donnees ANSD » de la page Pipeline (administrateur), ou a la
main. Ne remplace rien tant que l'ANSD n'a rien change :

  1. telecharge les jeux du script 35 dans un dossier temporaire ;
  2. compare leurs empreintes sha256 a celles de la copie actuelle (MANIFEST.json) ;
     identiques : rien n'est touche, seule la date de verification est notee ;
  3. sinon, met la nouvelle copie en place (l'ancienne est gardee de cote), relance la
     correspondance des codes (script 36) et l'exposition projetee (script 37) ;
  4. si une etape echoue, remet l'ancienne copie et relance le script 36 sur elle :
     ClimatSen garde un etat coherent, et l'erreur est notee.

L'etat est ecrit dans data/raw/ansd/odp/.synchro.json (lu par la page Pipeline) :
etat (en_cours, termine, erreur), resultat (inchange, mis_a_jour), fichiers modifies,
dates et fin du journal. L'API ouverte relit les fichiers des qu'ils changent ; la
plateforme, a l'expiration de son cache (5 minutes).

Usage : py -3 scripts/38_synchroniser_ansd.py
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = RACINE / "scripts"
ODP = RACINE / "data" / "raw" / "ansd" / "odp"
NOUVEAU = ODP.parent / ".odp_nouveau"
ANCIEN = ODP.parent / ".odp_ancien"
ETAT = ODP / ".synchro.json"


def maintenant():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def script35():
    spec = importlib.util.spec_from_file_location(
        "telecharger_odp", SCRIPTS / "35_telecharger_odp_ansd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ecrire_etat(**champs):
    etat = {}
    if ETAT.exists():
        try:
            etat = json.loads(ETAT.read_text(encoding="utf-8"))
        except ValueError:
            etat = {}
    etat.update(champs, mis_a_jour_le=maintenant())
    ODP.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lancer(script, journal):
    """Execute un script du projet ; leve une erreur s'il echoue."""
    r = subprocess.run([sys.executable, str(SCRIPTS / script)], cwd=str(RACINE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    journal.append(f"$ {script} (code {r.returncode})")
    journal.extend((r.stdout + r.stderr).strip().splitlines()[-12:])
    if r.returncode != 0:
        raise RuntimeError(f"{script} a echoue (code {r.returncode})")


def remplacer(source, cible):
    """Copie les fichiers de `source` dans `cible` (sans l'etat de synchronisation)."""
    cible.mkdir(parents=True, exist_ok=True)
    for f in source.iterdir():
        if f.is_file() and f.name != ETAT.name:
            shutil.copy2(f, cible / f.name)


def main():
    journal = []
    ecrire_etat(etat="en_cours", debut=maintenant(), fin=None, resultat=None,
                fichiers_modifies=[], erreur=None, journal=[])
    s35 = script35()
    ancien = s35.lire_manifeste(ODP)
    shutil.rmtree(NOUVEAU, ignore_errors=True)
    try:
        nouveaux = s35.telecharger(NOUVEAU)
    except Exception as e:                          # noqa: BLE001
        shutil.rmtree(NOUVEAU, ignore_errors=True)
        ecrire_etat(etat="erreur", fin=maintenant(),
                    erreur=f"API de l'ANSD injoignable ou réponse invalide : {e}",
                    journal=traceback.format_exc().splitlines()[-6:])
        print("Erreur de telechargement, rien n'a ete modifie :", e)
        return 1

    modifies = s35.fichiers_modifies(ancien, nouveaux)
    verifie = maintenant()
    if not modifies:
        shutil.rmtree(NOUVEAU, ignore_errors=True)
        ecrire_etat(etat="termine", fin=verifie, resultat="inchange",
                    derniere_verification=verifie, fichiers_modifies=[],
                    journal=["Données identiques à la copie actuelle : rien n'a été modifié."])
        print("Donnees de l'ANSD inchangees : rien n'a ete modifie.")
        return 0

    journal.append("Fichiers modifiés par l'ANSD : " + ", ".join(modifies))
    shutil.rmtree(ANCIEN, ignore_errors=True)
    if ODP.exists():
        remplacer(ODP, ANCIEN)
    try:
        remplacer(NOUVEAU, ODP)
        lancer("36_correspondance_zones_ansd.py", journal)
        lancer("37_exposition_projetee.py", journal)
    except Exception as e:                          # noqa: BLE001
        journal.append(f"Échec : {e}. Retour à la copie précédente.")
        if ANCIEN.exists():
            remplacer(ANCIEN, ODP)
            try:
                lancer("36_correspondance_zones_ansd.py", journal)
            except Exception as e2:                 # noqa: BLE001
                journal.append(f"La correspondance n'a pas pu être recalculée : {e2}")
        ecrire_etat(etat="erreur", fin=maintenant(), derniere_verification=verifie,
                    fichiers_modifies=modifies, erreur=str(e), journal=journal[-30:])
        print("\n".join(journal))
        return 1
    finally:
        shutil.rmtree(NOUVEAU, ignore_errors=True)

    shutil.rmtree(ANCIEN, ignore_errors=True)
    ecrire_etat(etat="termine", fin=maintenant(), resultat="mis_a_jour",
                derniere_verification=verifie, derniere_mise_a_jour=maintenant(),
                fichiers_modifies=modifies, journal=journal[-30:])
    print("\n".join(journal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
