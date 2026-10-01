#!/usr/bin/env python3
"""Controle des tableaux ANSD transcrits a la main (EHCVM 2021-2022, Atlas RGPH-5 2023).

Les CSV de data/raw/ansd/ ont ete recopies depuis les PDF (texte, ou lecture des pages
rendues en image quand le texte n'est pas extractible). Ce script verifie :
  1. EHCVM, Tableau VII-11 (assainissement par region) : chaque ligne totalise 100 %.
  2. EHCVM, cartes et figures regionales : moyenne des regions ponderee par leur part de
     population (Tableau III-2) comparee a la valeur nationale publiee. Controle
     approximatif pour les indicateurs mesures en menages (la part de population n'est
     pas la part des menages) ; un ecart de plusieurs points signale une definition
     differente ou une erreur de transcription.
  3. EHCVM, Tableau VIII-2 (chocs par milieu) : la valeur nationale est comprise entre
     le minimum et le maximum des milieux.
  4. Atlas RGPH-5 : chaque departement cite existe parmi les 46 de l'indice ; aucun
     departement n'est a la fois dans la classe haute et la classe basse d'une carte ;
     les classes de densite de l'Atlas sont comparees a la densite calculee par le
     script 26 (population RGPH-5 / superficie OCHA).

Ecrit le compte rendu dans data/raw/ansd/controle_transcriptions.txt.

Usage : py -3 scripts/30_controle_transcriptions_ansd.py
"""
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
ANSD = RACINE / "data" / "raw" / "ansd"
DEP = RACINE / "outputs" / "vulnerabilite" / "indice_risque_departements.csv"

# Valeurs nationales publiees dans le rapport EHCVM (page du PDF).
NATIONAL = {
    "acces_eau_potable_menages_pct": (93.7, "p. 80, texte VII.2.2.1"),
    "acces_electricite_menages_pct": (82.3, "p. 78, texte VII.2.1.2"),
    "insecurite_alimentaire_moderee_ou_grave_pct": (29.9, "p. 93, Figure VIII-3"),
    "insecurite_alimentaire_grave_pct": (3.9, "p. 93, Figure VIII-3"),
    "menages_ayant_subi_un_choc_3_ans_pct": (62.0, "p. 95, Figure VIII-5"),
}
SEUIL_ECART = 2.0  # points de pourcentage


def main():
    lignes = []

    def dire(texte=""):
        lignes.append(texte)
        print(texte)

    pauv = pd.read_csv(ANSD / "ehcvm_2021-2022_pauvrete_par_region.csv")
    poids = pauv.set_index("region")["part_population_pct"]
    dire("== Tableau III-2 (pauvrete) : somme des parts de population %.1f %%, "
         "des contributions %.1f %%" % (poids.sum(), pauv["contribution_c0_pct"].sum()))

    ass = pd.read_csv(ANSD / "ehcvm_2021-2022_assainissement_par_region.csv")
    somme = ass.drop(columns="region").sum(axis=1)
    dire("== Tableau VII-11 (assainissement) : totaux par region de %.1f a %.1f %%"
         % (somme.min(), somme.max()))
    for r, s in zip(ass["region"], somme):
        if abs(s - 100) > 0.2:
            dire("   ECART %s : %.1f %%" % (r, s))

    srv = pd.read_csv(ANSD / "ehcvm_2021-2022_services_chocs_par_region.csv").set_index("region")
    if set(srv.index) != set(poids.index):
        dire("   REGIONS DIFFERENTES du Tableau III-2 : %s" % sorted(set(srv.index) ^ set(poids.index)))
    dire("== Indicateurs regionaux : moyenne ponderee (part de population) vs national")
    for col, (nat, ref) in NATIONAL.items():
        moy = (srv[col] * poids.reindex(srv.index)).sum() / poids.reindex(srv.index).sum()
        etat = "ok" if abs(moy - nat) <= SEUIL_ECART else "ECART"
        dire("   %-45s moyenne %.1f / national %.1f (%s) -> %s" % (col, moy, nat, ref, etat))

    ch = pd.read_csv(ANSD / "ehcvm_2021-2022_chocs_par_milieu.csv")
    dire("== Tableau VIII-2 (chocs par milieu) : national entre min et max des milieux")
    for _, r in ch.iterrows():
        vals = [r["dakar_pct"], r["autres_urbains_pct"], r["rural_pct"]]
        etat = "ok" if min(vals) <= r["national_pct"] <= max(vals) else "ECART"
        dire("   %-40s %s" % (r["choc"], etat))

    atl = pd.read_csv(ANSD / "atlas_rgph5_2023_classes_extremes_departements.csv")
    dep = pd.read_csv(DEP, encoding="utf-8")
    inconnus = sorted(set(atl["departement"]) - set(dep["departement"]))
    dire("== Atlas RGPH-5 : %d lignes, %d cartes, departements inconnus : %s"
         % (len(atl), atl["indicateur"].nunique(), inconnus or "aucun"))
    for ind, g in atl.groupby("indicateur"):
        haut = set(g.loc[g["groupe"] == "classe_haute", "departement"])
        bas = set(g.loc[g["groupe"] == "classe_basse", "departement"])
        doublons = g[g.duplicated(["groupe", "departement"])]["departement"].tolist()
        dire("   %-24s haute %2d, basse %2d%s%s" % (
            ind, len(haut), len(bas),
            ", DANS LES DEUX : %s" % sorted(haut & bas) if haut & bas else "",
            ", DOUBLONS : %s" % doublons if doublons else ""))

    dire("== Densite : classes de l'Atlas vs densite du script 26 (RGPH-5 / superficie OCHA)")
    d = dep.set_index("departement")["densite_2023_hab_km2"]
    den = atl[atl["indicateur"] == "densite"]
    haut = set(den.loc[den["groupe"] == "classe_haute", "departement"])
    bas = set(den.loc[den["groupe"] == "classe_basse", "departement"])
    for nom in sorted(haut):
        dire("   classe > 349 : %-12s calcule %8.0f %s" % (nom, d[nom], "ok" if d[nom] > 349 else "DIFFERENT"))
    for nom in sorted(bas):
        dire("   classe < 39  : %-12s calcule %8.0f %s" % (nom, d[nom], "ok" if d[nom] < 39 else "DIFFERENT"))
    hors = sorted(set(d[d > 349].index) - haut) + sorted(set(d[d < 39].index) - bas)
    dire("   departements dans une classe extreme selon le calcul mais non cites par l'Atlas : %s"
         % (hors or "aucun"))

    (ANSD / "controle_transcriptions.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
