#!/usr/bin/env python3
"""Lance un script du pipeline (ou une chaine de scripts) en arriere-plan.

Appele par la page Pipeline (scripts/taches_fond.py), jamais a la main :
    python scripts/lancer_tache.py <nom> <script.py> [arguments...]
    python scripts/lancer_tache.py <nom> --chaine <a.py> <b.py> ...

Une chaine execute les scripts dans l'ordre, sans argument, et S'ARRETE A LA
PREMIERE ERREUR : une etape en aval ne doit pas tourner sur les sorties
perimees d'une etape amont en echec.

Ecrit dans outputs/taches/ :
  <nom>.json  etat (en_cours, termine, erreur, annule), code de sortie, dates,
              etapes d'une chaine, et "vu_le", rafraichi toutes les 5 s : une
              tache dont "vu_le" ne bouge plus a ete interrompue ;
  <nom>.log   sortie des scripts (stdout + stderr), relue par la page.
Un fichier <nom>.annuler demande l'arret.

L'etat est ecrit par CE processus, pas devine par la page a partir d'un PID :
os.kill(pid, 0), qui sert de test sous Linux, TUE le processus sous Windows.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "outputs" / "taches"
PAS = 5


def maintenant():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ecrire(chemin, etat):
    tmp = chemin.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(chemin)


def executer(script, args, journal, fichier_etat, etat, annuler, env):
    """Execute un script ; renvoie (code, annule)."""
    journal.write("\n[%s] === %s %s\n" % (maintenant(), script, " ".join(args)))
    journal.flush()
    proc = subprocess.Popen([sys.executable, str(RACINE / "scripts" / script)] + list(args),
                            cwd=str(RACINE), env=env, stdout=journal,
                            stderr=subprocess.STDOUT)
    dernier = time.time()
    while proc.poll() is None:
        time.sleep(0.5)          # fin et annulation vues vite ; etat ecrit toutes les PAS s
        if annuler.exists():
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            proc.wait()
            journal.write("\n[%s] annule\n" % maintenant())
            return proc.returncode, True
        if time.time() - dernier >= PAS:
            dernier = time.time()
            etat["vu_le"] = maintenant()
            ecrire(fichier_etat, etat)
    code = proc.wait()
    journal.write("\n[%s] fin de %s, code %s\n" % (maintenant(), script, code))
    journal.flush()
    return code, False


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: lancer_tache.py <nom> <script.py> [arguments...] | "
                 "<nom> --chaine <a.py> <b.py> ...")
    nom = sys.argv[1]
    if sys.argv[2] == "--chaine":
        scripts, args = sys.argv[3:], []
        chaine = True
    else:
        scripts, args = [sys.argv[2]], sys.argv[3:]
        chaine = False
    DOSSIER.mkdir(parents=True, exist_ok=True)
    fichier_etat = DOSSIER / (nom + ".json")
    annuler = DOSSIER / (nom + ".annuler")
    annuler.unlink(missing_ok=True)
    etat = {"nom": nom, "script": scripts[0] if not chaine else "chaine",
            "arguments": args, "etat": "en_cours", "debut": maintenant(),
            "vu_le": maintenant(), "pid": os.getpid()}
    if chaine:
        etat["etapes"] = [{"script": s, "etat": "en_attente"} for s in scripts]
        etat["total"] = len(scripts)
    ecrire(fichier_etat, etat)

    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    code, annule = 0, False
    with open(DOSSIER / (nom + ".log"), "w", encoding="utf-8") as journal:
        journal.write("[%s] debut : %s\n" % (maintenant(), " -> ".join(scripts)))
        for k, script in enumerate(scripts):
            if chaine:
                etat["etape_courante"] = k + 1
                etat["etapes"][k].update(etat="en_cours", debut=maintenant())
                ecrire(fichier_etat, etat)
            code, annule = executer(script, args, journal, fichier_etat, etat, annuler, env)
            if chaine:
                etat["etapes"][k].update(
                    etat="annule" if annule else ("termine" if code == 0 else "erreur"),
                    code=code, fin=maintenant())
            if annule or code != 0:
                if chaine:
                    for reste in etat["etapes"][k + 1:]:
                        reste["etat"] = "non_lance"
                    if not annule:
                        journal.write("\n[%s] arret de la chaine : %s en erreur (code %s)\n"
                                      % (maintenant(), script, code))
                break
    annuler.unlink(missing_ok=True)
    etat.update(etat="annule" if annule else ("termine" if code == 0 else "erreur"),
                code=code, fin=maintenant(), vu_le=maintenant())
    ecrire(fichier_etat, etat)
    return code


if __name__ == "__main__":
    sys.exit(main())
