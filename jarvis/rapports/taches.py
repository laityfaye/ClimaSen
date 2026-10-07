"""Generation des rapports en arriere-plan, versions et garde des fichiers.

Un rapport prend de quelques secondes (gabarit) a une minute (redaction IA
et PDF): il ne peut pas tenir dans un tour d'outil. L'outil generate_report
enregistre donc une tache et rend la main; le widget suit la progression
(GET /jarvis/api/rapports/{id}), ouvre l'APERCU une fois le rapport pret, et
telecharge les fichiers.

Versions. Apres lecture de l'apercu, l'utilisateur demande des changements a
Iris (outil edit_report): texte a reformuler, zone ou periode a changer,
visuel a retirer ou a ajouter, retour a la version precedente. Chaque
modification produit une NOUVELLE version du meme rapport (meme identifiant):
l'apercu se met a jour et surligne ce qui a change. Les regles ne changent
pas: le texte modifie passe la meme verification (aucun chiffre hors des
faits), et les textes fixes (ANACIM, limites) sont reinseres par le code.

Garanties, les memes que pour les figures (jarvis/figures.py):
  - un rapport n'est lisible QUE par la session qui l'a demande; un
    identifiant inconnu, expire ou d'une autre session donne la meme reponse;
  - stockage borne: duree de vie, plafond par session et plafond global,
    nombre de versions par rapport;
  - debit: une tache en cours par session, et un quota horaire;
  - cache: la meme demande sur la meme version des donnees reutilise les
    fichiers deja produits (aucun nouvel appel au modele).
"""
import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import secrets
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path

from ..tools.common import normalise
from . import manifest, redaction, service
from . import spec as module_spec
from .collecteurs import CollecteImpossible
from .document import Liste, Paragraphe

log = logging.getLogger("jarvis.rapports")

ETAPES = ("En file d'attente", "Lecture des données de la plateforme",
          "Calcul des faits, cartes et graphiques", "Rédaction", "Mise en page",
          "Export HTML, Word et PDF", "Terminé")
EXTENSIONS = {"html": "html", "pdf": "pdf", "docx": "docx", "csv": "csv"}
FICHIERS = {"html": "rapport.html", "pdf": "rapport.pdf", "docx": "rapport.docx",
            "csv": "faits.csv"}
MAX_VERSIONS = 15
# Champs de la demande qu'une modification peut changer (memes noms que
# l'outil generate_report).
CHAMPS_SPEC = ("type", "zone", "zone_code", "year_min", "year_max", "phase", "season",
               "horizon", "metric", "audience")
_ETIQUETTE = re.compile(r"^\s*(figure|fig|f|tableau|tab|t)\s*\.?\s*(?:n[°o]\s*)?(\d{1,2})\s*$",
                        re.IGNORECASE)


class QuotaRapports(Exception):
    """Trop de rapports pour cette session (message lisible)."""


class ModificationImpossible(ValueError):
    """Demande de modification invalide (message lisible par le modele)."""


class ModificationRefusee(Exception):
    """Seul le texte devait changer, et la redaction n'a pas ete acceptee:
    aucune nouvelle version n'est creee; le message dit pourquoi."""


def cle_visuel(bloc, spec) -> str:
    """Identite d'un visuel calcule, independante de la zone: 'Decomposition de
    l'indice : Pikine' et '... : Rufisque' sont le meme visuel. Un visuel
    retire reste ainsi retire quand la zone ou la periode change."""
    titre = bloc.titre
    lieu = spec.lieu
    for nom in sorted({lieu.nom, lieu.departement, lieu.region, lieu.arrondissement},
                      key=lambda n: -len(n or "")):
        if nom:
            titre = titre.replace(nom, "")
    return normalise(titre)


class Version:
    """Etat complet d'une version: de quoi la relire, la modifier, y revenir."""

    def __init__(self, numero, spec, collecte, texte, journal, extras, exclus, rapport,
                 dossier, formats, notes, note_ia="", modifies=frozenset(),
                 retraits=frozenset()):
        self.numero = numero
        self.spec = spec
        self.collecte = collecte
        self.texte = texte
        self.journal = journal
        self.extras = list(extras)
        self.exclus = frozenset(exclus)
        self.rapport = rapport
        self.dossier = dossier
        self.formats = list(formats)
        self.notes = list(notes)
        self.note_ia = note_ia
        self.modifies = frozenset(modifies)
        # Visuels calcules retires par l'utilisateur, par cle_visuel.
        self.retraits = frozenset(retraits)
        self.cree_le = time.time()

    def retirables(self) -> set:
        return {id(b) for _, b in list(self.collecte.visuels) + self.extras}

    def etiquettes(self) -> dict:
        """'Figure 2' -> le bloc, numerotation de CETTE version."""
        sortie = {}
        for f in self.rapport.figures():
            sortie["Figure %d" % f.numero] = f
        for t in self.rapport.tableaux():
            sortie["Tableau %d" % t.numero] = t
        return sortie

    def vue(self) -> dict:
        return {"version": self.numero, "notes": list(self.notes), "note_iris": self.note_ia,
                "cree_le": dt.datetime.fromtimestamp(self.cree_le).strftime("%H:%M")}


class Tache:
    def __init__(self, session_id, spec, profile, cle_cache, params=None):
        self.id = "R" + secrets.token_hex(10)
        self.session_id = session_id
        self.spec = spec
        self.profile = profile
        self.cle_cache = cle_cache
        self.params = dict(params or {})
        self.statut = "en_cours"
        self.etape = ETAPES[0]
        self.cree_le = time.time()
        self.fini_le = None
        self.erreur = None
        self.titre = module_spec.LIBELLES_TYPE[spec.type]
        self.sous_titre = spec.lieu.libelle()
        self.depuis_cache = False
        self.versions = []
        self.modification_en_cours = None

    # Raccourcis sur la version courante (compatibilite et lisibilite).
    @property
    def courante(self):
        return self.versions[-1] if self.versions else None

    @property
    def dossier(self):
        return self.courante.dossier if self.courante else None

    @property
    def formats(self):
        return self.courante.formats if self.courante else []

    def vue(self) -> dict:
        etape = ETAPES.index(self.etape) if self.etape in ETAPES else 0
        v = self.courante
        resume, redaction_mode, version_donnees = [], None, None
        if v is not None:
            resume = [b.texte for b in v.rapport.sections["resume"].blocs
                      if isinstance(b, Paragraphe)][:4]
            redaction_mode = v.rapport.meta.redaction
            version_donnees = v.rapport.meta.version_donnees
        return {"id": self.id, "statut": self.statut, "etape": self.etape,
                "progression": round(etape / float(len(ETAPES) - 1), 2),
                "titre": self.titre, "sous_titre": self.sous_titre, "type": self.spec.type,
                "formats": list(self.formats), "erreur": self.erreur, "resume": resume,
                "redaction": redaction_mode, "version_donnees": version_donnees,
                "hypotheses": list(self.spec.hypotheses), "depuis_cache": self.depuis_cache,
                "version": v.numero if v else 0,
                "versions": [x.vue() for x in self.versions],
                "modification_en_cours": self.modification_en_cours}


def _slug(texte):
    t = normalise(texte)[:40]
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "senegal"


def _etiquette(texte):
    m = _ETIQUETTE.match(str(texte))
    if not m:
        raise ModificationImpossible("Visuel à retirer non reconnu : %r. Désigne-le comme "
                                     "« Figure 2 » ou « Tableau 1 »." % texte)
    genre = "Figure" if m.group(1).lower().startswith("f") else "Tableau"
    return "%s %d" % (genre, int(m.group(2)))


class GestionnaireRapports:
    def __init__(self, dossier, claude=None, ttl_seconds=86400, max_par_session=10,
                 maximum=200, par_heure=6, simultanes=2, avec_pdf=True, redaction_ia=True,
                 gazetteer=None, bulletins=None):
        self.dossier = Path(dossier)
        self.claude = claude
        self.ttl = ttl_seconds
        self.max_par_session = max_par_session
        self.maximum = maximum
        self.par_heure = par_heure
        self.avec_pdf = avec_pdf
        self.redaction_ia = redaction_ia
        self._taches = OrderedDict()
        self._cache = {}
        self._verrou = threading.Lock()
        self._semaphore = None
        self._simultanes = simultanes
        self._boucle = None
        self._gazetteer = gazetteer
        self._bulletins = bulletins
        self.clarification = module_spec.EtatClarification()

    # --- dependances paresseuses ----------------------------------------------
    def gazetteer(self):
        if self._gazetteer is None:
            from . import gazetteer
            self._gazetteer = gazetteer.charger()
        return self._gazetteer

    def bulletins(self):
        if self._bulletins is not None:
            return self._bulletins
        try:
            from veille import production
            return production.bulletins_disponibles()
        except Exception:
            return []

    def attacher(self, boucle) -> None:
        """Boucle d'evenements du service: les taches y tournent, meme lancees
        depuis le fil d'un outil (asyncio.to_thread)."""
        self._boucle = boucle
        self._semaphore = asyncio.Semaphore(self._simultanes)

    def _client(self):
        return self.claude if self.redaction_ia else None

    # --- demande --------------------------------------------------------------
    def preparer(self, params, session_id, aujourd_hui=None) -> dict:
        deja = self.clarification.deja_posee(session_id)
        r = module_spec.preparer(params, self.gazetteer(), self.bulletins(), aujourd_hui,
                                 question_deja_posee=deja)
        if r["statut"] == "question":
            self.clarification.noter(session_id)
        else:
            self.clarification.effacer(session_id)
        return r

    def _quota(self, session_id):
        maintenant = time.time()
        miennes = [t for t in self._taches.values() if t.session_id == session_id]
        if any(t.statut == "en_cours" for t in miennes):
            raise QuotaRapports("Un rapport est déjà en cours de préparation pour cette "
                                "session : attendez qu'il soit prêt.")
        recentes = [t for t in miennes if maintenant - t.cree_le < 3600 and not t.depuis_cache]
        if len(recentes) >= self.par_heure:
            raise QuotaRapports("Limite de %d rapports par heure atteinte : réessayez plus tard."
                                % self.par_heure)

    def lancer(self, session_id, spec, profile="public", params=None) -> Tache:
        """Enregistre la tache et la demarre (appelable depuis n'importe quel fil)."""
        version = manifest.lire().get("version_donnees", "")
        cle = hashlib.sha256(json.dumps(
            [spec.cle(), version, profile if self.redaction_ia else "gabarit"],
            sort_keys=True, default=str).encode()).hexdigest()
        with self._verrou:
            self._purger_verrouille()
            self._quota(session_id)
            tache = Tache(session_id, spec, profile, cle, params)
            source = self._taches.get(self._cache.get(cle))
            if source is not None and source.statut == "termine" and source.versions:
                premiere = source.versions[0]
                tache.versions.append(Version(
                    1, premiere.spec, premiere.collecte, premiere.texte, premiere.journal,
                    premiere.extras, premiere.exclus, premiere.rapport, premiere.dossier,
                    premiere.formats, ["Rapport repris d'une demande identique"]))
                tache.titre, tache.sous_titre = source.titre, source.sous_titre
                tache.statut, tache.etape, tache.fini_le = "termine", ETAPES[-1], time.time()
                tache.depuis_cache = True
            miennes = [t for t in self._taches.values() if t.session_id == session_id]
            if len(miennes) >= self.max_par_session:
                self._oublier_verrouille(miennes[0].id)
            while len(self._taches) >= self.maximum:
                self._oublier_verrouille(next(iter(self._taches)))
            self._taches[tache.id] = tache
        if not tache.depuis_cache:
            self._demarrer(self._executer(tache))
        return tache

    def _demarrer(self, coro):
        try:
            boucle_courante = asyncio.get_running_loop()
        except RuntimeError:
            boucle_courante = None
        if boucle_courante is not None and (self._boucle is None or boucle_courante is self._boucle):
            if self._semaphore is None:
                self.attacher(boucle_courante)
            boucle_courante.create_task(coro)
        elif self._boucle is not None:
            asyncio.run_coroutine_threadsafe(coro, self._boucle)
        else:  # pas de service (scripts, tests synchrones): execution immediate
            asyncio.run(coro)

    async def _sous_semaphore(self, coro):
        if self._semaphore is not None:
            async with self._semaphore:
                return await coro
        return await coro

    async def _executer(self, tache):
        async def etape(texte):
            tache.etape = texte
        try:
            await self._sous_semaphore(self._produire(tache, etape))
        except CollecteImpossible as exc:
            tache.statut, tache.erreur = "echec", str(exc)
        except Exception:
            log.exception("Echec du rapport %s", tache.id)
            tache.statut = "echec"
            tache.erreur = "Le rapport n'a pas pu être produit (erreur interne)."
        finally:
            tache.fini_le = time.time()

    def _ecrire(self, tache, numero, rapport, sorties, journal, notes):
        dossier = self.dossier / tache.id / ("v%d" % numero)
        dossier.mkdir(parents=True, exist_ok=True)
        formats = []
        for fmt, nom in FICHIERS.items():
            contenu = sorties.get("faits_csv" if fmt == "csv" else fmt)
            if contenu:
                (dossier / nom).write_bytes(contenu)
                formats.append(fmt)
        (dossier / "meta.json").write_text(json.dumps({
            "id": tache.id, "version": numero, "spec": rapport.meta.spec, "journal": journal,
            "notes": notes,
            "meta": {"genere_le": rapport.meta.genere_le,
                     "version_donnees": rapport.meta.version_donnees,
                     "commit": rapport.meta.commit},
            "erreurs_export": sorties.get("erreurs")}, ensure_ascii=False, indent=1,
            default=str), encoding="utf-8")
        return dossier, formats

    async def _produire(self, tache, etape):
        details = {}
        rapport, collecte, journal, sorties = await service.produire(
            tache.id, tache.spec, client=self._client(), profile=tache.profile,
            gazetteer=self.gazetteer(), etape=etape, avec_pdf=self.avec_pdf, details=details)
        dossier, formats = self._ecrire(tache, 1, rapport, sorties, journal, [])
        tache.versions.append(Version(1, tache.spec, collecte, details["texte"], journal,
                                      details["extras"], frozenset(), rapport, dossier,
                                      formats, ["Première version"]))
        tache.titre, tache.sous_titre = rapport.meta.titre, rapport.meta.sous_titre
        tache.statut, tache.etape = "termine", ETAPES[-1]
        with self._verrou:
            self._cache[tache.cle_cache] = tache.id
        log.info("Rapport %s produit (%s, redaction %s, %s).", tache.id, tache.spec.type,
                 journal.get("mode"), ", ".join(formats))

    # --- modification ------------------------------------------------------------
    def modifier(self, session_id, rapport_id, demande) -> dict:
        """Prepare et lance une nouvelle version (appelable depuis n'importe quel fil).

        demande: instruction (texte), changes (champs de la demande initiale),
        remove_visuals (['Figure 2', ...]), reference_figures, extra_figures,
        revert (bool). Renvoie {"statut": "lance", ...} ou, si un nouveau champ
        est ambigu, la question de clarification (meme regle qu'a la creation).
        """
        from . import figures_reference, moteur_figures
        tache = self.obtenir(session_id, rapport_id) if rapport_id else self.dernier(session_id)
        if tache is None:
            raise ModificationImpossible("Aucun rapport à modifier dans cette session.")
        if tache.statut != "termine" or not tache.versions:
            raise ModificationImpossible("Le rapport n'est pas encore prêt : attendez la fin de "
                                         "sa préparation avant de le modifier.")
        if len(tache.versions) >= MAX_VERSIONS:
            raise ModificationImpossible("Ce rapport a déjà %d versions : générez-en un nouveau."
                                         % MAX_VERSIONS)
        courante = tache.courante
        plan = {"notes": [], "spec": None, "retraits": set(), "cles": set(), "extras": [],
                "instruction": "", "retour": None}

        if demande.get("revert"):
            if len(tache.versions) < 2:
                raise ModificationImpossible("Il n'y a pas de version précédente.")
            plan["retour"] = tache.versions[-2]
            plan["notes"].append("Retour à la version %d" % tache.versions[-2].numero)
        else:
            changes = {k: v for k, v in (demande.get("changes") or {}).items()
                       if k in CHAMPS_SPEC and v is not None}
            if changes:
                params = dict(tache.params)
                if "zone" in changes:
                    params.pop("zone_code", None)
                if "zone_code" in changes:
                    params.pop("zone", None)
                params.update(changes)
                r = self.preparer(params, session_id)
                if r["statut"] == "question":
                    return r
                nouvelle = r["spec"]
                if nouvelle.cle() != courante.spec.cle():
                    plan["spec"] = nouvelle
                    plan["params"] = params
                    plan["notes"].append(_decrire_changement(courante.spec, nouvelle))
            etiquettes = courante.etiquettes()
            retirables = courante.retirables()
            for brut in demande.get("remove_visuals") or []:
                cle = _etiquette(brut)
                bloc = etiquettes.get(cle)
                if bloc is None:
                    raise ModificationImpossible("%s n'existe pas dans la version %d (visuels : %s)."
                                                 % (cle, courante.numero, ", ".join(etiquettes)))
                if id(bloc) not in retirables:
                    raise ModificationImpossible("%s (%s) fait partie de la traçabilité du rapport "
                                                 "et ne peut pas être retiré." % (cle, bloc.titre))
                if any(b is bloc for _, b in courante.collecte.visuels):
                    plan["cles"].add(cle_visuel(bloc, courante.spec))
                else:
                    plan["retraits"].add(id(bloc))
                plan["notes"].append("%s retiré(e) : %s" % (cle, bloc.titre))
            for ident in demande.get("reference_figures") or []:
                try:
                    bloc = figures_reference.figure(ident)
                except KeyError as exc:
                    raise ModificationImpossible(str(exc).strip("'\""))
                plan["extras"].append(("analyse", bloc))
                plan["notes"].append("Figure ajoutée : %s" % bloc.titre)
            for brute in demande.get("extra_figures") or []:
                try:
                    bloc, _ = moteur_figures.pour_rapport(brute)
                except moteur_figures.SpecInvalide as exc:
                    raise ModificationImpossible("Figure demandée impossible : %s" % exc)
                plan["extras"].append(("analyse", bloc))
                plan["notes"].append("%s ajouté(e) : %s" % (
                    "Tableau" if bloc.__class__.__name__ == "Tableau" else "Figure", bloc.titre))
            instruction = str(demande.get("instruction") or "").strip()
            if instruction:
                plan["instruction"] = instruction[:redaction.MAX_INSTRUCTION]
                plan["notes"].append("Texte : " + (instruction[:160]
                                                   + ("…" if len(instruction) > 160 else "")))
            autres = plan["spec"] or plan["retraits"] or plan["cles"] or plan["extras"]
            if not (autres or plan["instruction"]):
                raise ModificationImpossible("Aucune modification à appliquer : précise ce qui "
                                             "doit changer (texte, zone, période, visuel).")
            if plan["instruction"] and not autres and self._client() is None:
                raise ModificationImpossible("Les modifications de texte demandent la rédaction "
                                             "assistée, indisponible sur ce serveur. Les changements "
                                             "de zone, de période ou de visuels restent possibles.")
            plan["autres"] = bool(autres)
        with self._verrou:
            if tache.statut == "en_cours":
                raise ModificationImpossible("Une modification est déjà en cours sur ce rapport.")
            tache.statut, tache.etape, tache.erreur = "en_cours", ETAPES[0], None
            tache.modification_en_cours = "; ".join(plan["notes"])
        self._demarrer(self._executer_modification(tache, plan))
        return {"statut": "lance", "rapport_id": tache.id, "titre": tache.titre,
                "sous_titre": tache.sous_titre, "version": courante.numero + 1,
                "modifications": plan["notes"]}

    async def _executer_modification(self, tache, plan):
        async def etape(texte):
            tache.etape = texte
        courante = tache.courante
        try:
            await self._sous_semaphore(self._modifier(tache, plan, etape))
            tache.erreur = None
        except CollecteImpossible as exc:
            tache.erreur = "Modification impossible : %s" % exc
        except ModificationRefusee as exc:
            tache.erreur = str(exc)
        except Exception:
            log.exception("Echec de la modification du rapport %s", tache.id)
            tache.erreur = "La modification n'a pas pu être appliquée (erreur interne)."
        finally:
            if tache.courante is courante and tache.erreur is None:
                tache.erreur = "La modification n'a pas pu être appliquée."
            tache.statut, tache.etape = "termine", ETAPES[-1]
            tache.modification_en_cours = None
            tache.fini_le = time.time()

    async def _modifier(self, tache, plan, etape):
        courante = tache.courante
        numero = courante.numero + 1
        note_ia = ""
        notes = list(plan["notes"])
        client = self._client()
        if plan["retour"] is not None:
            base = plan["retour"]
            spec, collecte, texte, journal = base.spec, base.collecte, base.texte, base.journal
            extras, exclus, retraits = base.extras, base.exclus, base.retraits
        else:
            spec, collecte = courante.spec, courante.collecte
            texte, journal = courante.texte, courante.journal
            extras = list(courante.extras) + plan["extras"]
            ids_extras = {id(b) for _, b in extras}
            exclus_extras = (courante.exclus & ids_extras) | plan["retraits"]
            retraits = courante.retraits | frozenset(plan["cles"])
            if plan["spec"] is not None:
                spec = plan["spec"]
                await etape("Calcul des faits, cartes et graphiques")
                collecte, _ = await asyncio.to_thread(service.preparer_collecte, spec,
                                                      self.gazetteer())
                await etape("Rédaction")
                texte, journal = await redaction.rediger(collecte, spec, client, tache.profile)
            if plan["instruction"]:
                await etape("Rédaction")
                nouveau, journal_m, note_ia = await redaction.modifier(
                    collecte, spec, client, texte, plan["instruction"], tache.profile)
                if nouveau is not None and nouveau == texte and not plan.get("autres"):
                    # Le modele a garde le texte (demande contraire aux regles,
                    # donnee absente): pas de version vide, l'explication suffit.
                    raise ModificationRefusee(note_ia or "Le texte n'a pas été modifié.")
                if nouveau is not None:
                    texte, journal = nouveau, journal_m
                elif not plan.get("autres"):
                    raise ModificationRefusee(note_ia or "La modification n'a pas été appliquée.")
                else:
                    notes = [n for n in notes if not n.startswith("Texte : ")]
                    notes.append("Texte inchangé")
            # Visuels calcules retires: reperes par leur cle, valable pour la
            # nouvelle collecte si la zone ou la periode a change.
            exclus = frozenset(exclus_extras) | frozenset(
                id(b) for _, b in collecte.visuels if cle_visuel(b, spec) in retraits)
        await etape("Mise en page")
        await etape("Export HTML, Word et PDF")
        rapport, sorties = await asyncio.to_thread(
            service.finaliser, tache.id, spec, collecte, texte, journal, extras, exclus, numero,
            self.avec_pdf)
        from .rendus.html import empreintes
        modifies = {t for t in empreintes(rapport) - empreintes(courante.rapport)
                    if tache.id not in t}
        dossier, formats = self._ecrire(tache, numero, rapport, sorties, journal, notes)
        tache.versions.append(Version(numero, spec, collecte, texte, journal, extras, exclus,
                                      rapport, dossier, formats, notes, note_ia, modifies,
                                      retraits))
        tache.spec = spec
        if plan.get("params"):
            tache.params = plan["params"]
        tache.titre, tache.sous_titre = rapport.meta.titre, rapport.meta.sous_titre
        log.info("Rapport %s : version %d (%s).", tache.id, numero, "; ".join(notes))

    # --- lecture -----------------------------------------------------------------
    def obtenir(self, session_id, rapport_id):
        with self._verrou:
            t = self._taches.get(rapport_id)
            if t is None or t.session_id != session_id:
                return None
            if time.time() - t.cree_le > self.ttl:
                self._oublier_verrouille(rapport_id)
                return None
            return t

    def dernier(self, session_id):
        with self._verrou:
            miennes = [t for t in self._taches.values() if t.session_id == session_id]
        return self.obtenir(session_id, miennes[-1].id) if miennes else None

    def fichier(self, session_id, rapport_id, fmt):
        """(octets, nom de fichier) de la version courante, ou None."""
        t = self.obtenir(session_id, rapport_id)
        if t is None or not t.versions or fmt not in t.formats or t.dossier is None:
            return None
        chemin = t.dossier / FICHIERS[fmt]
        if not chemin.is_file():
            return None
        date = dt.datetime.now().strftime("%Y%m%d")
        version = t.courante.numero
        nom = "CLIMATSEN_%s_%s_%s%s.%s" % (t.spec.type, _slug(t.spec.lieu.nom), date,
                                           "_v%d" % version if version > 1 else "",
                                           EXTENSIONS[fmt])
        if fmt == "csv":
            nom = nom.replace(".csv", "_faits.csv")
        return chemin.read_bytes(), nom

    def apercu(self, session_id, rapport_id):
        """HTML d'apercu de la version courante, changements surlignes."""
        t = self.obtenir(session_id, rapport_id)
        if t is None or not t.versions:
            return None
        from .rendus.html import en_html
        v = t.courante
        return en_html(v.rapport, modifies=set(v.modifies) if v.numero > 1 else None)

    def lire(self, session_id, rapport_id=None) -> dict:
        """Plan du rapport courant, pour que le modele sache de quoi parle
        l'utilisateur ('le deuxieme paragraphe', 'la figure 3')."""
        t = self.obtenir(session_id, rapport_id) if rapport_id else self.dernier(session_id)
        if t is None:
            raise ModificationImpossible("Aucun rapport dans cette session.")
        if not t.versions:
            return {"rapport_id": t.id, "statut": t.statut, "etape": t.etape,
                    "message": "Le rapport est encore en préparation."}
        v = t.courante
        retirables = v.retirables()
        sections = []
        for s in v.rapport.dans_l_ordre():
            paragraphes, listes = [], []
            for b in s.blocs:
                if isinstance(b, Paragraphe):
                    paragraphes.append(b.texte[:420] + ("…" if len(b.texte) > 420 else ""))
                elif isinstance(b, Liste) and s.cle == "conclusions":
                    listes.extend(b.elements)
            entree = {"section": s.titre, "paragraphes": paragraphes}
            if listes:
                entree["recommandations"] = listes
            if s.cle in ("methodologie", "annexes"):
                entree = {"section": s.titre, "note": "texte fixe inséré par la plateforme"}
            sections.append(entree)
        visuels = [{"etiquette": e, "titre": b.titre,
                    "retirable": id(b) in retirables}
                   for e, b in v.etiquettes().items()]
        return {"rapport_id": t.id, "statut": t.statut, "titre": t.titre,
                "sous_titre": t.sous_titre, "version": v.numero,
                "demande": v.spec.vue(), "sections": sections, "visuels": visuels,
                "historique": [x.vue() for x in t.versions],
                "regle": ("Les chiffres de ce plan viennent du rapport: cite-les tels quels. "
                          "Pour changer le rapport, appelle edit_report.")}

    # --- menage ----------------------------------------------------------------------
    def _oublier_verrouille(self, rapport_id):
        t = self._taches.pop(rapport_id, None)
        if t is None:
            return
        for cle, ident in list(self._cache.items()):
            if ident == rapport_id:
                del self._cache[cle]
        # Une tache servie depuis le cache pointe sur les fichiers de sa source:
        # on considere son propre dossier ET ceux qu'elle emprunte, et l'on ne
        # supprime que ceux qu'aucune tache restante n'utilise (sinon le dossier
        # d'une source purgee la premiere ne serait jamais efface).
        candidats = {self.dossier / t.id}
        candidats.update(v.dossier.parent for v in t.versions if v.dossier is not None)
        restants = [v.dossier for autre in self._taches.values() for v in autre.versions
                    if v.dossier is not None]
        for dossier in candidats:
            if dossier.parent != self.dossier:
                continue                      # garde-fou: jamais hors du dossier des rapports
            if not any(d == dossier or dossier in d.parents for d in restants):
                shutil.rmtree(dossier, ignore_errors=True)

    def _purger_verrouille(self):
        limite = time.time() - self.ttl
        for ident in [t.id for t in self._taches.values() if t.cree_le < limite]:
            self._oublier_verrouille(ident)

    def purger(self) -> int:
        with self._verrou:
            avant = len(self._taches)
            self._purger_verrouille()
            self.clarification.purger()
            return avant - len(self._taches)

    def taille(self) -> int:
        with self._verrou:
            return len(self._taches)


def _decrire_changement(avant, apres) -> str:
    morceaux = []
    if avant.type != apres.type:
        morceaux.append("type : %s" % module_spec.LIBELLES_TYPE[apres.type])
    if avant.lieu.code != apres.lieu.code:
        morceaux.append("zone : %s → %s" % (avant.lieu.nom, apres.lieu.nom))
    if (avant.annee_debut, avant.annee_fin) != (apres.annee_debut, apres.annee_fin):
        morceaux.append("période : %d-%d" % (apres.annee_debut, apres.annee_fin))
    if avant.phase != apres.phase:
        morceaux.append("phase : %s" % apres.phase)
    if avant.saison != apres.saison:
        morceaux.append("saison : %s" % apres.saison)
    if avant.metrique != apres.metrique:
        morceaux.append("métrique : %s" % apres.metrique)
    if avant.public != apres.public:
        morceaux.append("public : %s" % apres.public)
    return "Demande modifiée (" + ", ".join(morceaux or ["paramètres"]) + ")"
