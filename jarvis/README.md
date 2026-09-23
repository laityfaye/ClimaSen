# Jarvis CLIMAT-SEN — backend

Assistant IA de la plateforme CLIMAT-SEN, adossé à l'API Claude (Anthropic).
Un seul cerveau, deux profils d'accès : **public** (widget en lecture seule) et
**admin** (Laity, accès complet — Phase 4).

État : **livré**. Les six phases sont en place. **Une seule interface** : la
bulle Jarvis du dashboard. On y tape son mot de passe dans le champ de saisie
pour passer en profil administrateur.

---

## Démarrer en local

```bash
# 1. Dépendances
py -3 -m pip install -r jarvis/requirements.txt

# 2. Configuration
cp .env.example .env
py -3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → JARVIS_SECRET_KEY
#   puis renseigner ANTHROPIC_API_KEY dans .env

# 3. Backend Jarvis (port 8000)
py -3 -m uvicorn jarvis.app:create_app --factory --reload --port 8000

# 4. Dashboard, dans un second terminal (port 8501)
py -3 -m streamlit run scripts/dashboard.py
```

La bulle Jarvis apparaît en bas à droite du dashboard.

Vérification rapide sans navigateur :

```bash
curl http://localhost:8000/jarvis/health
# {"status":"ok",...,"configured":true,"env":"dev","tools":5}
```

Documentation d'API interactive en dev : <http://localhost:8000/jarvis/docs>
(fermée automatiquement quand `JARVIS_ENV=prod`).

## Tests

```bash
py -3 -m pytest tests/test_jarvis_*.py -q
```

Aucun test ne joint l'API Anthropic : le client Claude est remplacé par un
double (`FakeClaude` dans `tests/conftest.py`). **La suite ne coûte rien.**

Pour lancer l'ensemble du dépôt (Jarvis + téléconnexions, 581 tests, ~3 min) :

```bash
py -3 -m pytest tests/ -q
```

---

## Architecture

```
Widget Streamlit (iframe)          Interface admin (Phase 4)
            │                                │
            └────────────┬───────────────────┘
                         ▼
              FastAPI — jarvis/app.py
                         │
   ┌────────────┬────────┴────────┬──────────────┐
   ▼            ▼                 ▼              ▼
session.py   ratelimit.py   conversations.py   claude_client.py
(HMAC)       (token bucket)  (historique       (SDK Anthropic,
                              + plafonds)       streaming, erreurs)
```

| Fichier | Rôle |
|---|---|
| `app.py` | routes, SSE, gestion d'erreurs, assemblage |
| `config.py` | configuration par variables d'environnement |
| `session.py` | jetons signés HMAC-SHA256, révocation des sessions |
| `auth.py` | mot de passe administrateur (scrypt) |
| `actions.py` | propositions en attente d'approbation |
| `documents.py` | lecture et modification des .docx |
| `admin/admin.html` | console d'administration |
| `conversations.py` | historique serveur, TTL et plafonds |
| `ratelimit.py` | seau à jetons par session+IP |
| `claude_client.py` | seul point de contact avec le SDK Anthropic |
| `logging_conf.py` | logs JSON, flux public / admin séparés |
| `prompts/system_public.md` | prompt système du profil public |
| `tools/` | outils de lecture (données et documents) |
| `knowledge/` | index documentaire et moteur de recherche (Phase 3) |
| `widget/widget.html` | bulle de chat autonome |

### Les outils

| Outil | Lit | Répond à |
|---|---|---|
| `get_sst_index` | `load_sst` | valeur d'un indice SST, série mensuelle ou annuelle, extrêmes datés |
| `search_extreme_events` | `load_events` | combien d'événements, quand, où, lesquels ont été les plus intenses |
| `get_teleconnection` | `load_telecon` | corrélation indice / pluies extrêmes, par phase et par lag |
| `get_risk_cluster` | `load_clustering` | régimes océaniques du K-Means et leur profil |
| `search_documents` | index embarqué | méthodes, justifications, interprétations (mémoire et article) |

```
jarvis/tools/
  dataset.py    seul point de contact avec scripts/dashboard_utils.py
  registry.py   déclarations, permissions, exécution, plafond de taille
  common.py     vocabulaire de la plateforme, validation, formatage
  <outil>.py    une fonction pure run(params, data) par outil

jarvis/knowledge/
  texte.py         normalisation, racines, découpage (appliqué des deux côtés)
  bm25.py          index inversé et classement
  docx.py          lecture .docx par la bibliothèque standard
  corpus.json.gz   index construit hors ligne, versionné et déployé
```

**Une seule source de vérité.** Les outils passent par les loaders du dashboard,
jamais par une relecture maison des CSV. Si Jarvis et le module Téléconnexions
annonçaient deux chiffres différents pour la même question, la plateforme
perdrait sa crédibilité.

**Import paresseux.** `dashboard_utils` tire Streamlit, plotly et matplotlib
(~3 s). Il n'est importé qu'au premier besoin réel, et les loaders tournent dans
un thread : appelés directement dans une coroutine, ils gèleraient le serveur
pour tous les visiteurs. `JARVIS_TOOLS_PRELOAD=true` préchauffe le cache au
démarrage pour que le premier visiteur ne paie pas cette latence.

**Les clusters ne sont pas des zones géographiques.** Le K-Means porte sur le
champ SST global du jour de chaque événement : un cluster est une configuration
océanique. Les régions renvoyées par l'outil sont une conséquence observée (où
sont tombées les pluies), jamais le critère de classification. L'outil le
rappelle dans chaque réponse, et le prompt système en fait une règle.

### La base documentaire (Phase 3)

Le mémoire (18 400 mots) et l'article (10 200 mots) donnent à Jarvis de quoi
répondre aux questions de **méthode** : pourquoi CHIRPS, comment un événement
extrême est détecté, ce que corrige l'AR1. Les outils de données disent
*combien*, celui-ci dit *pourquoi*.

**Index construit hors ligne, embarqué dans le dépôt.** Les sources vivent dans
un dossier personnel hors du projet ; le serveur ne les aura jamais.
`scripts/15_build_jarvis_index.py` lit les `.docx` et écrit
`jarvis/knowledge/corpus.json.gz` (234 passages, 103 Ko), le seul fichier que
lit l'exécution. Aucune bibliothèque de documents, aucun appel réseau en
production.

**BM25 plutôt que des embeddings.** Sur 28 500 mots, un index inversé répond en
une fraction de milliseconde et tient dans 1 Mo, là où un modèle local
ajouterait des centaines de Mo de RAM et un service d'embeddings une clé d'API
de plus. Le vocabulaire des questions est celui du texte — téléconnexion,
CHIRPS, Niño 3.4 — soit le cas favorable du lexical. Et quand une formulation
échoue, **la boucle d'outils permet déjà au modèle de relancer la recherche**
avec d'autres termes : le rattrapage est architectural, pas statistique. Si le
rappel déçoit à l'usage, passer aux embeddings ne toucherait que `bm25.py`.

Trois réglages tirés de mesures, pas de principes :

- **le titre de section compte triple** — une section intitulée « 2.2
  Méthodologie de détection » traite du sujet, là où une conclusion peut citer
  les mêmes mots en passant ;
- **les synonymes du domaine sont appliqués à la requête** — le corpus dit
  « précipitations » là où un visiteur écrit « pluie », qui sans cette table ne
  touchait *aucun* passage ;
- **les doublons mémoire/article sont écartés** — les deux textes partagent des
  paragraphes identiques, les citer deux fois gaspille le contexte.

**L'index porte la version du traitement de texte.** Changer la tokenisation
sans reconstruire l'index ferait remonter des passages sans rapport, sans la
moindre erreur : le chargement refuse alors de servir et réclame une
reconstruction.

**Extraits plafonnés à 600 caractères.** Le mémoire n'est pas publié et le
widget est public et anonyme. Retirer une entrée de `CORPUS` dans le script de
construction suffit à exclure un document.

### Choix structurants

**Historique côté serveur.** Le client n'envoie qu'un `conversation_id`. S'il
renvoyait tout le fil, n'importe qui pourrait pousser 200 000 tokens dans une
requête et faire exploser la facture.

**Service séparé du dashboard.** `jarvis.service` et `climatsen.service` sont
deux unités systemd distinctes : une panne de Jarvis ne peut pas faire tomber la
plateforme.

**Préfixe `/jarvis` dans les routes elles-mêmes.** Le chemin est identique en
local et derrière nginx — aucune réécriture d'URL, donc aucune classe de bug
liée à la réécriture.

**Le profil est dans le jeton signé.** Un client ne peut pas se déclarer
`admin` : sans le secret serveur, le jeton est rejeté. La Phase 4 s'appuiera
dessus sans rien refondre.

---

## Endpoints

| Méthode | Route | Auth | Rôle |
|---|---|---|---|
| `GET` | `/jarvis/health` | — | état, modèle, `configured`, nombre d'outils |
| `POST` | `/jarvis/api/session` | — | émet un jeton anonyme |
| `POST` | `/jarvis/api/chat` | jeton | réponse en streaming (SSE) |
| `POST` | `/jarvis/api/chat/sync` | jeton | même chose, non streamée |
| `GET` | `/jarvis/api/conversation/{id}` | jeton | relit un fil |
| `GET` | `/jarvis/widget.html` | — | widget en autonome |
| `POST` | `/jarvis/api/admin/login` | — | ouvre une session admin |
| `POST` | `/jarvis/api/admin/logout` | jeton admin | ferme et révoque la session |
| `GET` | `/jarvis/api/admin/me` | jeton admin | état de la session |
| `GET` | `/jarvis/admin` | — | console d'administration |
| `GET` | `/jarvis/api/admin/actions` | jeton admin | propositions en attente |
| `POST` | `/jarvis/api/admin/actions/{id}/approve` | jeton admin | applique une proposition |
| `POST` | `/jarvis/api/admin/actions/{id}/reject` | jeton admin | refuse une proposition |

Le jeton passe dans l'en-tête `X-Jarvis-Session`.

Événements SSE : `meta` (conversation_id, modèle) → `tool`* (un par outil, juste
avant sa lecture) → `delta`* (fragments de texte) → `done` (usage en tokens
cumulé sur tous les tours). En cas de panne : `error` à la place de `done` — le
flux HTTP ayant déjà commencé, le statut ne peut plus changer.

L'événement `tool` porte `name` et `label` ; le widget affiche ce label pendant
la lecture. Sans ce signal, l'utilisateur voit plusieurs secondes de silence et
croit la bulle bloquée.

---

## Une seule interface

La bulle du dashboard est le seul point d'entrée. Pour passer en administrateur,
**tapez votre mot de passe dans le champ de saisie**, comme une question. Le
panneau change alors d'aspect — badge `ADMIN`, bordure corail, lien *Quitter* —
pour qu'on sache toujours à qui on parle.

### Le secret ne suit pas le chemin d'un message

Un message ordinaire est journalisé (extrait de 200 caractères), archivé dans
l'historique de conversation et transmis à l'API Anthropic. Un mot de passe ne
doit emprunter aucune de ces trois voies. L'interception a donc lieu **avant**
elles, dans `jarvis/elevation.py` : le message est reconnu, la session élevée,
et rien d'autre ne se produit. Trois tests le vérifient sur le contenu réel des
journaux, sur les appels reçus par le client Claude et sur la taille du magasin
de conversations.

Le widget **retire aussi la bulle** qui affichait le mot de passe : côté serveur
il n'a laissé aucune trace, mais il restait lisible à l'écran.

### Deux écueils qui dictent la forme du code

**Ne pas hacher chaque message.** Une vérification coûte 100 ms de `scrypt` :
répondre à toute question par un hachage serait un déni de service à bon marché.
Seuls les messages qui *ressemblent* à un mot de passe sont examinés — un seul
bloc, sans espace, longueur plausible. Une question en langage naturel contient
des espaces.

**Ne pas répondre « mot de passe invalide ».** Un visiteur qui tape un mot isolé
(« téléconnexions ») recevrait un refus au lieu d'une réponse. Une tentative
ratée retombe donc sur le chemin normal — mais sans recopier le texte dans les
journaux, puisque ce peut être un mot de passe mal tapé.

**Le raccourci n'ouvre pas un second guichet.** Les tentatives par le champ de
saisie consomment le **même** seau que la route de connexion : cinq essais par
quart d'heure et par adresse, partagés entre les deux chemins.

## Le profil administrateur (Phase 4)

```bash
py -3 -m jarvis.auth          # génère le haché, à coller dans .env
# puis redémarrer : uvicorn ne relit pas le .env à chaud
```

Console : <http://localhost:8000/jarvis/admin>

**Seul le haché est stocké**, en `scrypt` (bibliothèque standard : rien à
installer sur le serveur, et mémoire-dur, donc bien plus coûteux à attaquer
par GPU que PBKDF2). Le mot de passe en clair n'existe ni dans le code, ni dans
le `.env`, ni dans les logs — un test le vérifie sur le contenu réel des
fichiers de journal.

**Échouer toujours de la même façon.** Mot de passe faux, profil admin non
configuré, trop de tentatives : même message. Distinguer les deux premiers cas
dirait à un attaquant si la cible existe.

**La déconnexion ferme réellement la session.** Un jeton HMAC est autoporteur :
il reste valide jusqu'à son échéance même après un `logout`. Une liste de
révocation côté serveur le neutralise, et oublie l'entrée dès que le jeton a
expiré de lui-même.

**Ce que le profil change** : le modèle (`claude-opus-5`), le prompt système
(`prompts/system_admin.md`), le seau de débit (séparé du public — un afflux de
visiteurs ne doit pas bloquer l'administrateur) et le fichier de journal
(`admin.jsonl`). Les outils exposés suivront en Phase 5 : le registre filtre
déjà par profil et **revalide à l'exécution**.

Le profil vit dans le jeton signé : sans le secret serveur, on ne peut ni en
forger un, ni promouvoir un jeton public en modifiant sa charge. Les deux cas
sont testés.

## Les outils d'action (Phase 5)

`list_documents`, `find_in_document` et `propose_document_edit` — réservés au
profil admin, ils travaillent sur les **fichiers vivants**, pas sur l'index figé
qu'interroge `search_documents`.

### Pourquoi Jarvis ne peut pas écrire

Un outil qui accepterait un paramètre `confirmer=true` ne prouverait rien :
c'est le **modèle** qui compose les arguments. Il peut mettre ce drapeau
lui-même, par zèle ou parce qu'une instruction bien tournée l'y a poussé. Une
consigne de prompt ne protège pas un fichier.

D'où la séparation en deux chemins :

```
Jarvis  ──propose──>  registre d'actions  ──clic de l'utilisateur──>  serveur écrit
(outil)               (en attente, 30 min)   (route HTTP, pas un outil)
```

`propose_document_edit` dépose une proposition et **rend la main**. La route
`/approve` n'est pas un outil : le modèle ne peut pas l'appeler. Elle exige une
session admin, n'accepte que les propositions **de cette session**, refuse un
rejeu et refuse une proposition expirée.

Conséquence assumée : aucun outil d'action ne modifie quoi que ce soit dans le
tour où il est appelé. C'est exactement l'effet recherché.

### Ce que garantit l'écriture elle-même

- **Sauvegarde horodatée** avant toute modification (`*.avant-jarvis-*.docx`).
- **Seuls les nœuds `<w:t>` sont touchés** : un remplacement sur le XML entier
  atteindrait aussi les largeurs de tableau, où Word stocke des valeurs comme
  « 560 » en twips.
- **Écriture atomique** : fichier temporaire puis remplacement, pour qu'une
  interruption ne laisse pas un `.docx` tronqué.
- **Piste d'audit** dans `admin.jsonl` : quoi, par qui, combien d'occurrences,
  quelle sauvegarde.

Après une modification, l'index documentaire est périmé : relancer
`scripts/15_build_jarvis_index.py`.

## Ajouter un outil

1. Créer `jarvis/tools/<nom>.py` exposant `NAME`, `LABEL`, `PERMISSION`,
   `DATASETS`, `DESCRIPTION`, `SCHEMA` et une fonction pure
   `run(params, data) -> dict`, sans dépendance à FastAPI.
2. L'ajouter à `MODULES` dans `tools/registry.py`.
3. Écrire `tests/test_jarvis_tools_<nom>.py` : la fonction étant pure, elle se
   teste sur des DataFrames synthétiques, sans serveur, sans API, sans fichier.

Règles tenues par le registre, pas par les outils :

- **Permissions.** `specs_for()` n'expose que les outils du profil et
  `execute()` revalide. Un outil admin reste inexécutable depuis une session
  publique même si le modèle en devine le nom — et le message d'erreur est le
  même que pour un outil inexistant, pour ne pas confirmer son existence.
- **Erreurs.** Un paramètre invalide revient au modèle en `tool_result`
  d'erreur, rédigé en français avec les valeurs acceptées : il se corrige au
  tour suivant au lieu de faire échouer la requête.
- **Taille.** Chaque résultat est ramené sous `JARVIS_TOOL_RESULT_MAX_CHARS` en
  réduisant ses listes, jamais en coupant le JSON en plein milieu.

Les paramètres sont volontairement tolérants : `"nino 3.4"`, `"pleine saison"`,
`"kedougou"` sont acceptés. Le modèle n'écrit pas toujours la forme exacte du
fichier, et une erreur évitée est un appel API économisé.

## Revue de sécurité (Phase 6)

Deux failles **vérifiées exploitables** sur le code des phases précédentes, et
non théoriques : chacune a été reproduite avant d'être corrigée.

### 1. Anti-force brute contournable — `X-Forwarded-For`

*Constat : 12 tentatives de connexion, 12 adresses déclarées, **aucun
blocage**.*

nginx était configuré avec `$proxy_add_x_forwarded_for`, qui **conserve**
l'en-tête envoyé par le client et se contente d'ajouter l'adresse réelle à la
fin. Le code lisait la **première** valeur — précisément celle que le client
contrôle. Il suffisait d'en changer à chaque essai pour repartir d'un compteur
neuf : le mot de passe admin devenait attaquable à une dizaine d'essais par
seconde.

Corrigé sur deux plans, indépendants l'un de l'autre :

- **côté application** : l'en-tête n'est cru que si la requête vient d'un proxy
  de confiance (`JARVIS_TRUSTED_PROXIES`), et la valeur est lue **depuis la
  droite** — la seule que notre nginx écrit ;
- **côté nginx** : `X-Forwarded-For $remote_addr` **réécrit** l'en-tête au lieu
  de l'allonger, donc plus rien du client n'y subsiste.

### 2. Plafond de débit contournable — rotation de session

*Constat : 10 messages avec 10 jetons de session neufs depuis la même adresse,
**aucun blocage**.*

La clé du seau était `session_id|ip`. Or un jeton de session s'obtient **sans
authentification** : en demander un neuf à chaque message changeait la clé et
remettait le compteur à zéro. Le commentaire du code affirmait le contraire.

Il y a désormais **deux plafonds indépendants, tous deux à franchir** : un par
adresse (qu'on ne peut plus fuir) et un par session (qui borne une rafale et
évite qu'un seul visiteur derrière un NAT épuise le plafond commun). Le journal
indique lequel des deux a bloqué — sans quoi le réglage se ferait à l'aveugle.

### 3. Oracle temporel sur un profil non configuré

Sans mot de passe configuré, la réponse arrivait en 1 ms au lieu de 100 :
mesurer le temps de réponse suffisait à savoir qu'il n'y avait rien à chercher.
La vérification fait désormais le même travail, pour rien.

### En-têtes de sécurité

`Content-Security-Policy` (`default-src 'self'`, pas de ressource externe),
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, et `Strict-Transport-Security`
en production. La console affiche du texte produit par un modèle : l'échappement
du rendu est la première barrière, la CSP est celle qui tient si la première
cède.

### Ce que la revue n'a pas trouvé

Pas de traversée de répertoire (les outils ne manipulent que des **clés**
logiques, jamais un chemin venu du modèle), pas de secret dans les journaux
(vérifié sur leur contenu réel), pas d'élévation de profil (un jeton forgé ou
modifié est rejeté), pas d'écriture accessible au modèle (§ protocole
d'approbation).

## Coût et exploitation

Modèle public `claude-sonnet-5` : 2 $ / M tokens en entrée, 10 $ / M en sortie.

**Mesuré en conditions réelles** (22 septembre 2026) :

| | Phase 1 (sans outils) | Phase 2 (question chiffrée) |
|---|---|---|
| Appels API | 1 | 2 (un tour d'outils) |
| Coût par échange | 0,4 centime | ~1 centime |
| Pour 1 000 messages | ~4 $ | ~10 $ |

Le préfixe mis en cache est passé de 1 625 à ~5 550 tokens (les définitions
d'outils s'y ajoutent), relu à 10 % du prix à chaque appel. L'ordre du préfixe
étant `tools → system → messages`, la césure posée sur le bloc `system` couvre
aussi les outils : un seul point de cache à déclarer.

Un échange sans chiffre à lire ne déclenche aucun outil et reste au tarif de la
Phase 1. Deux outils demandés au même tour partent en parallèle : une seule
attente, pas deux.

Les compteurs d'usage remontent dans `outputs/jarvis_logs/public.jsonl`, une
ligne JSON par événement — chaque appel d'outil y est tracé avec sa durée et la
taille de son résultat :

```bash
py -3 -c "import pandas as pd; d=pd.read_json('outputs/jarvis_logs/public.jsonl', lines=True); print(d.groupby('message').size())"
```

Le rate limiting par défaut (12 en rafale, 6/minute) borne ce que peut consommer
un visiteur seul ; `JARVIS_MAX_TOOL_ROUNDS` borne ce que peut coûter une seule
question.

## Limites connues (Phase 6)

- **État en mémoire** : conversations, sessions et compteurs de débit vivent
  dans le process. Un redémarrage les efface, et plusieurs workers uvicorn ne
  les partageraient pas — d'où `--workers 1`. Passage à SQLite ou Redis à
  arbitrer en Phase 6 selon le trafic réel.
- **Recherche lexicale, pas sémantique.** Une question dont aucun mot ne figure
  dans le texte peut ne rien remonter. Le prompt demande au modèle d'envoyer des
  mots-clés et de reformuler une fois avant de conclure.
- **L'index n'est pas reconstruit tout seul.** Après modification du mémoire ou
  de l'article, relancer `scripts/15_build_jarvis_index.py`.
- **Les outils ne sont pas mémorisés.** Seul le texte final entre dans
  l'historique, pas les `tool_use`/`tool_result`. Une question de suivi
  (« et pour Niño 3 ? ») relance donc l'outil — quelques centaines de tokens,
  contre un historique qui gonflerait indéfiniment.
- **Un seul domaine d'action.** Seuls les documents sont modifiables.
  Bibliographie, git, serveur et courrier restent à faire — le protocole de
  proposition, lui, est écrit une fois pour toutes.
- **Les outils de rédaction sont inopérants en production.** Les `.docx` vivent
  dans un dossier personnel hors du dépôt : le serveur n'y a pas accès, et
  c'est voulu.
- **Propositions en mémoire.** Un redémarrage annule celles qui attendent —
  préférable à une écriture approuvable dont plus personne ne se souvient.
- **Tout l'état vit en mémoire** : conversations, compteurs de débit, sessions
  révoquées, propositions en attente. D'où `--workers 1`, qui n'est pas un
  détail : avec plusieurs processus, chacun aurait ses propres compteurs et les
  plafonds seraient multipliés d'autant. Le `limit_req` nginx est la deuxième
  ligne de défense, indépendante du nombre de processus.
- **Les journaux gardent un extrait des questions** (200 caractères), y compris
  côté public. Utile pour mesurer l'usage, à considérer si la plateforme
  s'ouvre largement : `JARVIS_LOG_PROMPTS=false` le désactive.

## Déploiement (préparé, non appliqué)

`deploy/jarvis.service` et le bloc `/jarvis/` ajouté à
`deploy/nginx-climatsen.conf`. Le `proxy_buffering off` y est indispensable :
sans lui, nginx accumule la réponse et la délivre d'un bloc, ce qui annule le
streaming.
