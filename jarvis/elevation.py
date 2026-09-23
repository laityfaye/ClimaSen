"""Elevation de session depuis le champ de saisie (interface unique).

Le widget est la seule interface: on y tape son mot de passe comme on taperait
une question, et la session passe en admin. Cela evite une seconde page de
connexion, mais fait passer un secret par le chemin d'un message ordinaire --
chemin qui journalise, archive et transmet a l'API Anthropic.

D'ou l'interception AVANT tout le reste. Un message reconnu comme tentative
d'elevation n'est jamais:
  - journalise (meme tronque)
  - ecrit dans l'historique de conversation
  - transmis au modele

Deux ecueils a eviter, qui dictent la forme du module:

1. Verifier chaque message coute 100 ms de scrypt. Repondre a toute question
   par un hachage serait un deni de service a bon marche. Seuls les messages
   qui RESSEMBLENT a un mot de passe sont examines: un seul bloc, sans espace,
   de longueur plausible. Une question en langage naturel contient des espaces.

2. Une tentative ratee ne doit pas repondre "mot de passe invalide": un
   visiteur qui tape un mot isole ("teleconnexion") recevrait un refus au lieu
   d'une reponse. Un echec retombe donc sur le chemin normal -- mais sans
   journaliser le texte, qui peut etre un mot de passe mal tape.
"""
import re

LONGUEUR_MINIMALE = 8
LONGUEUR_MAXIMALE = 256

# Un mot de passe saisi seul: aucun espace, aucun retour a la ligne.
_ESPACE = re.compile(r"\s")


def ressemble_a_un_mot_de_passe(message: str) -> bool:
    """Le message merite-t-il qu'on depense un hachage pour le verifier ?

    Volontairement etroit. Le but n'est pas de deviner l'intention, mais
    d'ecarter a coup sur tout ce qui est manifestement une question.
    """
    if not message:
        return False
    texte = message.strip()
    if len(texte) < LONGUEUR_MINIMALE or len(texte) > LONGUEUR_MAXIMALE:
        return False
    if _ESPACE.search(texte):
        return False
    # Un mot unique termine par un point d'interrogation reste une question.
    if texte.endswith(("?", "!", ".", ":")):
        return False
    return True
