"""Manifeste des donnees et index des figures de reference (rapports d'Iris).

A lancer en fin de pipeline et a chaque deploiement:

    py -3 scripts/32_manifest_donnees.py

Ecrit:
  - outputs/manifest.json: empreinte sha256 de chaque fichier lu par les
    rapports, version des donnees (imprimee sur chaque rapport), commit;
  - outputs/figures_reference_index.json: figures de reference disponibles
    (jarvis/rapports/figures_reference.yaml) et leur empreinte.

Code de sortie 1 si un fichier source ou une figure de reference manque:
un rapport produit sans eux serait incomplet.
"""
import hashlib
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from jarvis.rapports import figures_reference, manifest  # noqa: E402


def main():
    m = manifest.ecrire()
    print("Version des donnees : %s (code %s)" % (m["version_donnees"], m["commit"]))
    print("Fichiers : %d, absents : %s" % (len(m["fichiers"]), ", ".join(m["absents"]) or "aucun"))
    index, manquantes = [], []
    for e in figures_reference._entrees().values():
        chemin = RACINE / e["fichier"]
        if chemin.is_file():
            index.append({"id": e["id"], "fichier": e["fichier"], "types": e["types"],
                          "sha256": hashlib.sha256(chemin.read_bytes()).hexdigest()})
        else:
            manquantes.append(e["id"])
    sortie = RACINE / "outputs" / "figures_reference_index.json"
    sortie.write_text(json.dumps({"version_donnees": m["version_donnees"], "figures": index,
                                  "manquantes": manquantes}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print("Figures de reference : %d disponibles, manquantes : %s"
          % (len(index), ", ".join(manquantes) or "aucune"))
    return 1 if (m["absents"] or manquantes) else 0


if __name__ == "__main__":
    sys.exit(main())
