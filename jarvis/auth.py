"""Authentification du profil admin: hachage et verification du mot de passe.

Choix de scrypt plutot que bcrypt ou argon2: il est dans la bibliotheque
standard (hashlib), donc aucune dependance a installer sur le serveur, et il
est MEMOIRE-DUR -- une attaque par GPU ou ASIC y est bien plus couteuse qu'avec
PBKDF2, qui ne coute que du calcul.

Le mot de passe en clair n'existe nulle part: ni dans le code, ni dans le .env,
ni dans les logs. Seul le hache est stocke, et il porte ses propres parametres,
ce qui permettra de les durcir plus tard sans invalider l'existant.

Format stocke (une seule ligne, sans espace):

    scrypt$<n>$<r>$<p>$<sel base64>$<hache base64>

Generer un hache:

    py -3 -m jarvis.auth
"""
import base64
import hashlib
import hmac
import secrets

# Parametres par defaut: ~100 ms et 16 Mio par verification sur une machine
# courante. Assez lent pour rendre une attaque hors ligne penible, assez rapide
# pour que la connexion reste instantanee a l'usage.
N_DEFAUT = 2 ** 14
R_DEFAUT = 8
P_DEFAUT = 1
LONGUEUR_CLE = 32
LONGUEUR_SEL = 16
MAXMEM = 64 * 1024 * 1024

LONGUEUR_MINIMALE = 12


class MotDePasseInvalide(ValueError):
    """Mot de passe refuse a la creation (trop court, vide)."""


def _b64e(brut: bytes) -> str:
    return base64.b64encode(brut).decode("ascii")


def _b64d(texte: str) -> bytes:
    return base64.b64decode(texte.encode("ascii"))


def hacher(mot_de_passe: str, n: int = N_DEFAUT, r: int = R_DEFAUT,
           p: int = P_DEFAUT) -> str:
    """Retourne la chaine a coller dans JARVIS_ADMIN_PASSWORD_HASH."""
    if not isinstance(mot_de_passe, str) or not mot_de_passe.strip():
        raise MotDePasseInvalide("Le mot de passe ne peut pas etre vide.")
    if len(mot_de_passe) < LONGUEUR_MINIMALE:
        raise MotDePasseInvalide(
            "Le mot de passe doit faire au moins %d caracteres." % LONGUEUR_MINIMALE
        )
    sel = secrets.token_bytes(LONGUEUR_SEL)
    hache = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=sel,
                           n=n, r=r, p=p, dklen=LONGUEUR_CLE, maxmem=MAXMEM)
    return "scrypt$%d$%d$%d$%s$%s" % (n, r, p, _b64e(sel), _b64e(hache))


def _decoder(stocke: str):
    """Retourne (n, r, p, sel, hache) ou leve ValueError."""
    morceaux = stocke.strip().split("$")
    if len(morceaux) != 6 or morceaux[0] != "scrypt":
        raise ValueError("format de hache inconnu")
    n, r, p = int(morceaux[1]), int(morceaux[2]), int(morceaux[3])
    return n, r, p, _b64d(morceaux[4]), _b64d(morceaux[5])


def verifier(mot_de_passe: str, stocke: str) -> bool:
    """Verifie un mot de passe contre un hache stocke.

    Ne leve jamais: un hache mal forme ou absent renvoie False. Une exception
    ici distinguerait "mal configure" de "mauvais mot de passe" dans la reponse
    HTTP, ce qui renseignerait un attaquant.
    """
    if not mot_de_passe or not stocke:
        return False
    try:
        n, r, p, sel, attendu = _decoder(stocke)
        candidat = hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=sel,
                                  n=n, r=r, p=p, dklen=len(attendu), maxmem=MAXMEM)
    except (ValueError, TypeError, MemoryError):
        return False
    # Comparaison a temps constant: une comparaison naive fuirait, par le
    # temps de reponse, le nombre d'octets corrects en tete.
    return hmac.compare_digest(candidat, attendu)


def _principal() -> int:  # pragma: no cover - utilitaire interactif
    """Genere un hache depuis le terminal, sans jamais afficher le mot de passe."""
    import getpass
    import sys

    print("Generation du hache administrateur Jarvis")
    print("Le mot de passe n'est ni affiche, ni enregistre, ni journalise.\n")
    try:
        mot_de_passe = getpass.getpass("Mot de passe (%d caracteres minimum) : "
                                       % LONGUEUR_MINIMALE)
        confirmation = getpass.getpass("Confirmer : ")
    except (EOFError, KeyboardInterrupt):
        print("\nAnnule.")
        return 1

    if mot_de_passe != confirmation:
        print("\nLes deux saisies different.")
        return 1
    try:
        hache = hacher(mot_de_passe)
    except MotDePasseInvalide as exc:
        print("\n%s" % exc)
        return 1

    print("\nColler cette ligne dans le fichier .env :\n")
    print("JARVIS_ADMIN_PASSWORD_HASH=%s\n" % hache)
    print("Puis redemarrer le service: uvicorn ne relit pas le .env a chaud.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(_principal())
