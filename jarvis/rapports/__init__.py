"""Rapports professionnels generes par Iris a partir des donnees de CLIMAT-SEN.

Principe directeur: le CODE calcule et dessine, le modele ne fait que rediger.

    demande en langage naturel
      -> spec.py           fiche structuree (type, zone, periode, phase, public)
                           + une seule question de clarification si besoin
      -> collecteurs/      faits chiffres et visuels, par les memes chargeurs
                           que le dashboard (jarvis/tools/dataset.py)
      -> redaction.py      prose redigee par Claude avec des renvois
                           {{fait:id}}: il ne tape jamais un chiffre
      -> verification.py   nombres, lexique de certitude, structure;
                           repli sur la redaction gabarit en cas d'echec
      -> document.py       modele de document unique
      -> rendus/           HTML, PDF (Chromium headless), Word (python-docx)

Chaque chiffre du rapport vient d'un Fait du registre (faits.py), qui porte
sa source, sa periode et son statut: observe, correle ou projete. Chaque
visuel porte titre, legende, unite, periode et source, sinon il est refuse a
la construction. La version des donnees (manifest.py) est imprimee sur
chaque page.
"""
TYPES = ("historique", "teleconnexions", "vulnerabilite", "veille")
PUBLICS = ("decideur", "technique")
HORIZONS = ("prochaine", "en_cours")
LIBELLES_TYPE = {
    "historique": "Rapport historique des pluies extrêmes (1981-2023)",
    "teleconnexions": "Rapport téléconnexions océan / pluies extrêmes",
    "vulnerabilite": "Rapport de vulnérabilité (indice de risque par zone)",
    "veille": "Bulletin de veille pré-saison",
}
