"""De la collecte et de la redaction au document final.

Ordre fixe des sections (document.SECTIONS). Le code insere ici, APRES la
redaction, tout ce que le modele ne doit pas pouvoir alterer: hypotheses,
mentions officielles, avertissements, methodologie, sources, limites et
tracabilite. Les renvois {{fait:id}} sont remplaces par les valeurs du
registre, et le statut de chaque paragraphe est recalcule a partir des faits
qu'il cite.
"""
import datetime as dt

from . import textes_fixes as tf
from . import verification
from .document import Encadre, Liste, Meta, Paragraphe, Rapport, Tableau


def _paragraphes(rapport, section, blocs, registre):
    for p in blocs:
        texte = p["texte"] if isinstance(p, dict) else p[0]
        propose = (p.get("statut") if isinstance(p, dict) else p[1])
        if propose == "aucun":
            propose = None
        statut = verification.statut_de(texte, registre, propose)
        rapport.ajouter(section, Paragraphe(registre.remplacer(texte).strip(), statut))


def assembler(rapport_id, spec, collecte, redaction, journal, manifeste, extras=(),
              exclus=frozenset(), version=1):
    """extras: [(section, bloc)] figures a la demande ou de reference.
    exclus: id() des visuels retires a la demande de l'utilisateur."""
    reg = collecte.registre
    maintenant = dt.datetime.now(dt.timezone.utc)
    meta = Meta(
        id=rapport_id, type=spec.type, titre=collecte.titre, sous_titre=collecte.sous_titre,
        genere_le=maintenant.strftime("%Y-%m-%d %H:%M UTC"),
        version_donnees=manifeste.get("version_donnees", "inconnue"),
        commit=manifeste.get("commit", "inconnu"), redaction=journal.get("mode", "gabarit"),
        modele=journal.get("modele", "aucun"), public=tf.PUBLICS[spec.public],
        zone=collecte.zone, periode=collecte.periode, hypotheses=list(spec.hypotheses),
        spec=spec.vue(), version=version)
    r = Rapport(meta)

    # --- 1. titre et contexte ---------------------------------------------------
    _paragraphes(r, "contexte", redaction["contexte"], reg)
    if spec.hypotheses:
        r.ajouter("contexte", Encadre(" ".join(spec.hypotheses),
                                      "hypothese", "Hypothèses retenues"))
    for m in collecte.mentions:
        if m.genre == "officiel":
            r.ajouter("contexte", m)

    # --- 2. resume executif ---------------------------------------------------------
    _paragraphes(r, "resume", redaction["resume"], reg)
    for m in collecte.mentions:
        if m.genre == "avertissement":
            r.ajouter("resume", m)

    # --- 3. methodologie et sources ---------------------------------------------------
    r.ajouter("methodologie", Paragraphe(tf.METHODOLOGIES[spec.type], "methode"))
    r.ajouter("methodologie", Paragraphe(tf.LEGENDE_STATUTS, None))
    r.ajouter("methodologie", Liste([tf.SOURCES[k] for k in collecte.sources if k in tf.SOURCES]))
    r.ajouter("methodologie", Paragraphe(
        "Tous les chiffres de ce rapport sont lus dans les données de la plateforme "
        "CLIMAT-SEN (version des données %s) ; aucune valeur n'est saisie à la main. La "
        "rédaction %s." % (meta.version_donnees,
                           "a été assistée par un modèle de langage (%s), chaque valeur étant "
                           "insérée et vérifiée par le code" % meta.modele
                           if meta.redaction == "ia" else
                           "est produite par des gabarits automatiques"), "methode"))

    # --- 4. analyse ---------------------------------------------------------------------
    _paragraphes(r, "analyse", redaction["analyse"], reg)
    for section, bloc in list(collecte.visuels) + list(extras):
        if id(bloc) in exclus:
            continue
        r.ajouter("analyse" if section not in ("analyse", "conclusions") else section, bloc)

    # --- 5. conclusions et recommandations ------------------------------------------------
    _paragraphes(r, "conclusions", redaction["conclusions"], reg)
    recos = [reg.remplacer(x).strip() for x in redaction["recommandations"] if str(x).strip()]
    if recos:
        r.ajouter("conclusions", Liste(recos, ordonnee=True))
    if spec.type == "veille":
        r.ajouter("conclusions", Encadre(tf.MENTION_ANACIM, "officiel", "Rappel"))

    # --- 6. annexes : limites et tracabilite -------------------------------------------
    limites = [tf.LIMITES[k] for k in tf.ORDRE_LIMITES if k in collecte.limites]
    limites += collecte.limites_specifiques
    r.ajouter("annexes", Encadre("Limites à garder en tête pour interpréter ce rapport.",
                                 "limite", "Limites"))
    r.ajouter("annexes", Liste(limites))
    fichiers = manifeste.get("fichiers") or {}
    lignes = [[nom, e.get("chemin", ""), e.get("source", ""), e.get("periode", ""),
               (e.get("sha256") or "absent")[:12]] for nom, e in sorted(fichiers.items())]
    if lignes:
        r.ajouter("annexes", Tableau(
            ["Jeu", "Fichier", "Source", "Période", "Empreinte"], lignes,
            "Fichiers sources et empreintes",
            "Empreinte sha256 (12 premiers caractères) de chaque fichier lu par la plateforme : "
            "elle permet de vérifier qu'un rapport a été produit sur les mêmes données.",
            "sans objet", "voir colonne Période", "Manifeste CLIMAT-SEN (outputs/manifest.json)"))
    r.ajouter("annexes", Paragraphe(
        "Rapport %s, version %d, généré le %s. Version des données %s, code %s. Rédaction : %s. Le "
        "registre des %d faits chiffrés de ce rapport (valeur, unité, statut, période, source) "
        "est disponible au format CSV." % (
            meta.id, meta.version, meta.genere_le, meta.version_donnees, meta.commit,
            "assistée (%s)" % meta.modele if meta.redaction == "ia" else "gabarit automatique",
            len(reg)), None))
    return r.finaliser()
