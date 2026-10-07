"""Redaction contrainte des rapports: verification et repli sur le gabarit.

Aucun appel reseau: des faux clients jouent un modele honnete, un modele qui
invente un chiffre, un modele qui se corrige apres refus, un modele en panne.
"""
import asyncio
import json

import pytest

from jarvis.rapports import redaction, verification
from jarvis.rapports.collecteurs import Collecte
from jarvis.rapports.faits import RegistreFaits
from jarvis.rapports.gazetteer import PAYS
from jarvis.rapports.spec import ReportSpec


def _registre():
    r = RegistreFaits()
    r.ajouter("n", 229, "evenements", "observe", "CHIRPS", "1981-2023", format="entier")
    r.ajouter("record", 231.4, "max", "observe", "CHIRPS", "1981-2023", decimales=1,
              suffixe=" mm/jour")
    r.ajouter("r", -0.42, "r", "correle", "OISST", "1983-2023", format="signe")
    r.ajouter("proba", 0.307, "p", "projete", "C3S", "saison 2023", format="fraction_pct",
              decimales=0)
    r.ajouter("seuil", 50, "seuil", "methode", "methode", "1981-2023", format="entier")
    return r


def _redaction(**surcharges):
    base = {
        "contexte": [{"texte": "Rapport sur la période 1981-2023.", "statut": "aucun"}],
        "resume": [{"texte": "On compte {{fait:n}} événements ; record {{fait:record}}.",
                    "statut": "observe"}],
        "analyse": [{"texte": "Le lien avec l'AMO (r = {{fait:r}}) tend à être négatif.",
                     "statut": "correle"}],
        "conclusions": [{"texte": "La vigilance reste de mise.", "statut": "aucun"}],
        "recommandations": ["Curer les caniveaux avant juillet."],
    }
    base.update(surcharges)
    return base


def _permis(r):
    return verification.autorises(r, ["Seuil de 50 mm et 2 écarts-types.",
                                      "Période 1981-2023."])


# =============================================================================
# Verification
# =============================================================================
def test_redaction_conforme_acceptee():
    r = _registre()
    assert verification.verifier(_redaction(), r, _permis(r)) == []


def test_chiffre_invente_refuse():
    r = _registre()
    red = _redaction(resume=[{"texte": "On compte 312 événements.", "statut": "observe"}])
    motifs = verification.verifier(red, r, _permis(r))
    assert any("312" in m for m in motifs)


def test_chiffre_d_un_fait_tolere_en_clair():
    r = _registre()
    red = _redaction(resume=[{"texte": "On compte 229 événements, record 231,4 mm.",
                              "statut": "observe"}])
    assert verification.verifier(red, r, _permis(r)) == []


def test_annee_inventee_refusee():
    r = _registre()
    red = _redaction(analyse=[{"texte": "Comme en 1957, la saison fut terrible.",
                               "statut": "observe"}])
    assert any("1957" in m for m in verification.verifier(red, r, _permis(r)))


@pytest.mark.parametrize("texte", [
    "Un AMO froid provoquera des inondations.",
    "Ce lien garantit une saison humide.",
    "La saison sera certainement extrême.",
    "Il va pleuvoir fortement en août.",
    "Ce résultat démontre que l'océan cause les extrêmes.",
])
def test_langage_de_certitude_refuse(texte):
    r = _registre()
    red = _redaction(analyse=[{"texte": texte, "statut": "correle"}])
    assert any("certitude" in m for m in verification.verifier(red, r, _permis(r)))


def test_pretendre_remplacer_l_anacim_refuse():
    r = _registre()
    ok = _redaction(conclusions=[{"texte": "Ce bulletin ne remplace pas les alertes de "
                                           "l'ANACIM.", "statut": "aucun"}])
    assert verification.verifier(ok, r, _permis(r)) == []
    ko = _redaction(conclusions=[{"texte": "Ce bulletin remplace les alertes officielles.",
                                  "statut": "aucun"}])
    assert any("ANACIM" in m for m in verification.verifier(ko, r, _permis(r)))


def test_renvoi_inconnu_et_structure():
    r = _registre()
    assert any("inexistants" in m for m in verification.verifier(
        _redaction(resume=[{"texte": "{{fait:invente}}", "statut": "observe"}]), r, _permis(r)))
    assert verification.verifier(_redaction(analyse=[]), r, _permis(r))
    assert verification.verifier(_redaction(recommandations=[]), r, _permis(r))
    assert verification.verifier("pas un objet", r, set())


def test_resume_trop_long():
    r = _registre()
    long = " ".join(["mot"] * 300)
    assert any("trop long" in m for m in verification.verifier(
        _redaction(resume=[{"texte": long, "statut": "aucun"}]), r, _permis(r)))


def test_noms_a_chiffres_ne_sont_pas_des_valeurs():
    assert verification.nombres("Niño 3.4, ATL3, RGPH-5, C3S, IC 95 % et C7") == []
    assert verification.nombres("1 317 événements et 0,42") == ["1317", "0.42"]


@pytest.mark.parametrize("texte, propose, attendu", [
    ("p = {{fait:proba}} et r = {{fait:r}}", "observe", "projete"),
    ("r = {{fait:r}} pour {{fait:n}} cas", "observe", "correle"),
    ("{{fait:n}} événements", "projete", "observe"),
    ("Texte sans fait", "projete", None),
    ("Texte sans fait", "observe", "observe"),
    ("Seuil de {{fait:seuil}}", None, "methode"),
])
def test_statut_recalcule_depuis_les_faits(texte, propose, attendu):
    assert verification.statut_de(texte, _registre(), propose) == attendu


# =============================================================================
# Redaction avec repli
# =============================================================================
def _collecte():
    c = Collecte(registre=_registre(), titre="T", sous_titre="S", zone="Sénégal",
                 periode="1981-2023")
    c.paragraphe("contexte", "Rapport sur la période 1981-2023.")
    c.paragraphe("resume", "On compte {{fait:n}} événements.", "observe")
    c.paragraphe("analyse", "Lien r = {{fait:r}}.", "correle")
    c.paragraphe("conclusions", "Vigilance.", None)
    c.recommandations = ["Curer les caniveaux avant juillet."]
    return c


def _spec():
    return ReportSpec(type="historique", lieu=PAYS, annee_debut=1981, annee_fin=2023,
                      phase="Toutes phases", saison=None, metrique="max_precip",
                      public="decideur")


class FauxRedacteur:
    def __init__(self, reponses, erreur=None):
        self.reponses = list(reponses)
        self.erreur = erreur
        self.appels = []

    async def generer_json(self, system, messages, schema, profile="public", **kw):
        self.appels.append(messages)
        if self.erreur:
            raise self.erreur
        texte = self.reponses.pop(0)
        return {"text": texte if isinstance(texte, str) else json.dumps(texte),
                "usage": {"input_tokens": 10, "output_tokens": 5}, "model": "faux"}


def test_redaction_ia_acceptee():
    client = FauxRedacteur([_redaction()])
    red, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    assert journal["mode"] == "ia" and journal["tentatives"] == 1
    assert red["resume"][0]["texte"].startswith("On compte {{fait:n}}")
    assert journal["usage"]["input_tokens"] == 10


def test_le_modele_recoit_les_faits_et_le_schema():
    client = FauxRedacteur([_redaction()])
    asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    charge = json.loads(client.appels[0][0]["content"])
    assert {f["id"] for f in charge["faits"]} == {"n", "record", "r", "proba", "seuil"}
    assert "gabarit" in charge and "recommandations_gabarit" in charge


def test_chiffre_invente_puis_correction():
    ko = _redaction(resume=[{"texte": "On compte 999 événements.", "statut": "observe"}])
    client = FauxRedacteur([ko, _redaction()])
    red, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    assert journal["mode"] == "ia" and journal["tentatives"] == 2
    # Le second appel porte les motifs du refus.
    assert "999" in client.appels[1][-1]["content"]


def test_menteur_obstine_repli_sur_gabarit():
    ko = _redaction(resume=[{"texte": "On compte 999 événements.", "statut": "observe"}])
    client = FauxRedacteur([ko, ko, ko])
    red, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    assert journal["mode"] == "gabarit" and journal["tentatives"] == 3
    assert red["resume"][0]["texte"] == "On compte {{fait:n}} événements."
    assert "repli" in journal["modele"]


def test_json_invalide_puis_repli():
    client = FauxRedacteur(["pas du json", "{", "[]"])
    _, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    assert journal["mode"] == "gabarit"


def test_api_en_panne_repli_immediat():
    client = FauxRedacteur([], erreur=RuntimeError("timeout"))
    red, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), client))
    assert journal["mode"] == "gabarit" and journal["tentatives"] == 1
    assert red["recommandations"] == ["Curer les caniveaux avant juillet."]


def test_sans_client_gabarit():
    red, journal = asyncio.run(redaction.rediger(_collecte(), _spec(), None))
    assert journal["mode"] == "gabarit"


def test_gabarit_nettoye_des_faits_absents():
    c = _collecte()
    c.paragraphe("analyse", "Donnée locale : {{fait:absent}}.", "observe")
    c.recommandations.append("Préparer {{fait:absent2}}.")
    retirees = redaction.nettoyer_gabarit(c, c.registre)
    assert len(retirees) == 2
    assert all("absent" not in t for t, _ in c.gabarit["analyse"])
