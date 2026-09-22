# Jarvis CLIMAT-SEN — backend

Assistant IA de la plateforme CLIMAT-SEN, adossé à l'API Claude (Anthropic).
Un seul cerveau, deux profils d'accès : **public** (widget en lecture seule) et
**admin** (Laity, accès complet — Phase 4).

État : **Phase 2 — outils publics**. Chat de bout en bout, avec accès en
lecture seule aux données réelles de la plateforme. Pas encore de RAG.

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
# {"status":"ok",...,"configured":true,"env":"dev","tools":4}
```

Documentation d'API interactive en dev : <http://localhost:8000/jarvis/docs>
(fermée automatiquement quand `JARVIS_ENV=prod`).

## Tests

```bash
py -3 -m pytest tests/test_jarvis_*.py -q
```

Aucun test ne joint l'API Anthropic : le client Claude est remplacé par un
double (`FakeClaude` dans `tests/conftest.py`). **La suite ne coûte rien.**

Pour lancer l'ensemble du dépôt (Jarvis + téléconnexions, 392 tests, ~2 min) :

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
| `session.py` | jetons anonymes signés HMAC-SHA256 |
| `conversations.py` | historique serveur, TTL et plafonds |
| `ratelimit.py` | seau à jetons par session+IP |
| `claude_client.py` | seul point de contact avec le SDK Anthropic |
| `logging_conf.py` | logs JSON, flux public / admin séparés |
| `prompts/system_public.md` | prompt système du profil public |
| `tools/` | outils de lecture des données (Phase 2) |
| `widget/widget.html` | bulle de chat autonome |

### Les outils (Phase 2)

| Outil | Lit | Répond à |
|---|---|---|
| `get_sst_index` | `load_sst` | valeur d'un indice SST, série mensuelle ou annuelle, extrêmes datés |
| `search_extreme_events` | `load_events` | combien d'événements, quand, où, lesquels ont été les plus intenses |
| `get_teleconnection` | `load_telecon` | corrélation indice / pluies extrêmes, par phase et par lag |
| `get_risk_cluster` | `load_clustering` | régimes océaniques du K-Means et leur profil |

```
jarvis/tools/
  dataset.py    seul point de contact avec scripts/dashboard_utils.py
  registry.py   déclarations, permissions, exécution, plafond de taille
  common.py     vocabulaire de la plateforme, validation, formatage
  <outil>.py    une fonction pure run(params, data) par outil
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

Le jeton passe dans l'en-tête `X-Jarvis-Session`.

Événements SSE : `meta` (conversation_id, modèle) → `tool`* (un par outil, juste
avant sa lecture) → `delta`* (fragments de texte) → `done` (usage en tokens
cumulé sur tous les tours). En cas de panne : `error` à la place de `done` — le
flux HTTP ayant déjà commencé, le statut ne peut plus changer.

L'événement `tool` porte `name` et `label` ; le widget affiche ce label pendant
la lecture. Sans ce signal, l'utilisateur voit plusieurs secondes de silence et
croit la bulle bloquée.

---

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

## Limites connues (Phase 2)

- **État en mémoire** : conversations, sessions et compteurs de débit vivent
  dans le process. Un redémarrage les efface, et plusieurs workers uvicorn ne
  les partageraient pas — d'où `--workers 1`. Passage à SQLite ou Redis à
  arbitrer en Phase 6 selon le trafic réel.
- **Aucun RAG.** Jarvis lit les données chiffrées, pas la thèse ni l'article :
  il ne peut pas citer un passage de méthodologie. C'est l'objet de la Phase 3.
- **Les outils ne sont pas mémorisés.** Seul le texte final entre dans
  l'historique, pas les `tool_use`/`tool_result`. Une question de suivi
  (« et pour Niño 3 ? ») relance donc l'outil — quelques centaines de tokens,
  contre un historique qui gonflerait indéfiniment.
- **Profil admin non ouvert.** La plomberie existe, la branche est fermée.

## Déploiement (préparé, non appliqué)

`deploy/jarvis.service` et le bloc `/jarvis/` ajouté à
`deploy/nginx-climatsen.conf`. Le `proxy_buffering off` y est indispensable :
sans lui, nginx accumule la réponse et la délivre d'un bloc, ce qui annule le
streaming.
