"""Vue du dashboard (Phase 9): validation, blocs envoyes au modele, API.

La vue vient du navigateur: on verifie surtout ce qui ne doit pas passer
(faux PNG, image geante, champs trop longs, corps surdimensionne) et que
rien n'entre dans l'historique.
"""
import base64
import struct
import zlib

import pytest

from conftest import sse_events
from jarvis import page_view

CHAT = "/jarvis/api/chat"


def auth(token):
    return {"X-Jarvis-Session": token}


def png(largeur=4, hauteur=3):
    """Un vrai PNG minimal, construit octet par octet."""
    def bloc(genre, donnees):
        crc = zlib.crc32(genre + donnees) & 0xFFFFFFFF
        return struct.pack(">I", len(donnees)) + genre + donnees + struct.pack(">I", crc)
    ihdr = struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0)
    brut = b"".join(b"\x00" + b"\xff\x00\x00" * largeur for _ in range(hauteur))
    return (page_view.SIGNATURE_PNG + bloc(b"IHDR", ihdr)
            + bloc(b"IDAT", zlib.compress(brut)) + bloc(b"IEND", b""))


def data_url(octets):
    return page_view.PREFIXE_DATA + base64.b64encode(octets).decode()


VUE = {
    "page_titre": "Teleconnexions SST",
    "indicateurs": [{"libelle": "Tests totaux", "valeur": "66"}],
    "graphiques": [
        {"titre": "Heatmap par lag", "sous_titre": "Couleur = r",
         "resume": '{"traces":[{"type":"heatmap"}]}', "image": None},
    ],
}


# --- png_valide ------------------------------------------------------------------
def test_png_reel_accepte_avec_ou_sans_prefixe():
    octets = png()
    assert page_view.png_valide(data_url(octets)) == base64.b64encode(octets).decode()
    assert page_view.png_valide(base64.b64encode(octets).decode())


@pytest.mark.parametrize("image", [
    None, "",
    "data:image/png;base64,pas-du-base64!!",
    data_url(b"GIF89a" + b"\x00" * 40),                 # autre format
    data_url(b"<svg onload=alert(1)>" + b"\x00" * 40),
    data_url(page_view.SIGNATURE_PNG + b"\x00" * 10),    # tronque
])
def test_images_douteuses_ecartees(image):
    assert page_view.png_valide(image) is None


def test_dimensions_plafonnees():
    assert page_view.png_valide(data_url(png(2001, 10))) is None
    assert page_view.png_valide(data_url(png(10, 2001))) is None
    assert page_view.png_valide(data_url(png(2000, 10)))


# --- blocs ---------------------------------------------------------------------------
def test_blocs_texte_puis_images_etiquetees():
    vue = page_view.VueDashboard(**{**VUE, "graphiques": [
        {"titre": "A", "image": data_url(png())},
        {"titre": "B", "resume": "{}"},
        {"titre": "C", "image": data_url(png())},
    ]})
    blocs = page_view.blocs(vue)
    assert [b["type"] for b in blocs] == ["text", "text", "image", "text", "image"]
    assert blocs[0]["text"].startswith("<vue_dashboard>")
    assert "Tests totaux : 66" in blocs[0]["text"]
    assert "Graphique 2 : B" in blocs[0]["text"]
    assert blocs[1]["text"] == "Image du graphique 1 (A) :"
    assert blocs[3]["text"] == "Image du graphique 3 (C) :"
    assert blocs[2]["source"]["media_type"] == "image/png"


def test_trois_images_au_plus():
    vue = page_view.VueDashboard(graphiques=[
        {"titre": str(i), "image": data_url(png())} for i in range(4)])
    assert sum(1 for b in page_view.blocs(vue) if b["type"] == "image") == 3


def test_vue_vide_ne_produit_rien():
    assert page_view.blocs(None) == []
    assert page_view.blocs(page_view.VueDashboard()) == []


def test_journal_ne_garde_que_des_comptes():
    vue = page_view.VueDashboard(**{**VUE, "graphiques": [
        {"titre": "secret", "image": data_url(png())}]})
    assert page_view.resume_journal(vue) == {"graphiques": 1, "images": 1,
                                             "indicateurs": 1}


# --- API -----------------------------------------------------------------------------
def test_la_vue_part_vers_le_modele_avant_la_question(client, token):
    vue = {**VUE, "graphiques": [{**VUE["graphiques"][0], "image": data_url(png())}]}
    r = client.post(CHAT, json={"message": "Que montre ce graphique ?",
                                "page_context": {"page": "Teleconnexions"},
                                "page_view": vue}, headers=auth(token))
    assert r.status_code == 200
    blocs = client.fake.calls[-1]["messages"][-1]["content"]
    types = [b["type"] for b in blocs]
    assert types == ["text", "text", "text", "image", "text"]
    assert blocs[0]["text"].startswith("<contexte_dashboard>")
    assert blocs[1]["text"].startswith("<vue_dashboard>")
    assert blocs[-1]["text"] == "Que montre ce graphique ?"


def test_la_vue_n_entre_pas_dans_l_historique(client, token):
    premier = sse_events(client.post(
        CHAT, json={"message": "Q1", "page_view": VUE}, headers=auth(token)).text)
    conv = premier[0][1]["conversation_id"]
    client.post(CHAT, json={"message": "Q2", "conversation_id": conv},
                headers=auth(token))
    envoye = client.fake.calls[-1]["messages"]
    assert [m["content"] for m in envoye] == ["Q1", "Bonjour, je suis Jarvis.", "Q2"]


def test_faux_png_ignore_sans_bloquer(client, token):
    vue = {**VUE, "graphiques": [{"titre": "X", "image": data_url(b"GIF89a" + b"0" * 40)}]}
    r = client.post(CHAT, json={"message": "?", "page_view": vue}, headers=auth(token))
    assert r.status_code == 200
    blocs = client.fake.calls[-1]["messages"][-1]["content"]
    assert "image" not in [b["type"] for b in blocs]


@pytest.mark.parametrize("vue", [
    {"page_titre": "x" * 201},
    {"indicateurs": [{"libelle": "a", "valeur": "b"}] * 13},
    {"graphiques": [{"titre": "g"}] * 5},
    {"graphiques": [{"resume": "r" * 6001}]},
    {"graphiques": [{"image": "a" * (page_view.MAX_IMAGE_B64 + 100)}]},
])
def test_champs_hors_limites_rejetes_avant_tout_appel(client, token, vue):
    r = client.post(CHAT, json={"message": "?", "page_view": vue}, headers=auth(token))
    assert r.status_code == 422
    assert client.fake.calls == []


def test_corps_surdimensionne_refuse_avant_lecture(client, token):
    from jarvis.app import MAX_BODY_BYTES
    r = client.post(CHAT, content=b"{" + b" " * (MAX_BODY_BYTES + 10) + b"}",
                    headers={**auth(token), "Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    assert client.fake.calls == []


def test_trois_captures_reelles_passent_sous_le_plafond(client, token):
    """Trois images au plafond individuel: la requete doit rester acceptee."""
    grosse = data_url(png(900, 380))
    vue = {"graphiques": [{"titre": str(i), "image": grosse} for i in range(3)]}
    r = client.post(CHAT, json={"message": "?", "page_view": vue}, headers=auth(token))
    assert r.status_code == 200


def test_prompts_expliquent_la_vue():
    from jarvis.claude_client import load_system_prompt
    for nom in ("system_public", "system_admin"):
        assert "<vue_dashboard>" in load_system_prompt(nom)
