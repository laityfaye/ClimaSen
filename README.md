# ClimatSen

Plateforme d'aide à la décision sur les **pluies extrêmes au Sénégal** : détection
des événements extrêmes (CHIRPS, 1981-2023), liens avec la température des océans
(11 indices SST, décalages de 0 à 5 mois), veille pré-saison, indice de risque par
département et arrondissement croisé avec les données de l'ANSD, et **Iris**,
l'assistante IA qui répond aux questions à partir des données de la plateforme.

En ligne : https://climatsen.innosft.com

| Composant | Technologie | Port local |
|---|---|---|
| Plateforme (9 pages : Accueil, Événements, Indices SST, Téléconnexions, Clustering, Veille pré-saison, Vulnérabilité, Pipeline, À propos) | Streamlit | 8501 |
| Iris (assistante IA) et API ouverte des statistiques (`/api/v1`, JSON, CSV, GeoJSON, SDMX) | FastAPI + Uvicorn | 8010 |

Aucune base de données : les données sont des fichiers (CSV, NPZ, GeoJSON, JSON)
versionnés dans ce dépôt et lus en lecture seule.

## 1. Prérequis

- Linux (Ubuntu 22.04 / 24.04, utilisé en production) ou Windows 10/11.
- **Python 3.12 ou plus récent** (développé et testé en 3.13.3) : Python 3.11 refuse
  la syntaxe de certaines chaînes formatées.
- git ; environ 2 Go de disque ; 4 Go de mémoire (8 Go recommandés).
- Linux, si pip doit compiler h5py ou netCDF4 : `sudo apt-get install libhdf5-dev libnetcdf-dev`.
- Un accès Internet pour les fonds de carte et pour la conversation avec Iris.
- Windows : installer dans un **chemin court et sans accent**, par exemple
  `C:\ClimaSen`. Certains fichiers du dépôt ont un chemin relatif de 104 caractères :
  au-delà d'environ 150 caractères pour le dossier d'installation, Windows (limite de
  260) fait échouer le `git clone` (« Filename too long »). À défaut, cloner avec
  `git -c core.longpaths=true clone ...`. Les accents gênent netCDF4 et h5py (le code
  le contourne, mais pas tous les outils tiers).

## 2. Installation

```bash
git clone -b phase2-0 https://github.com/laityfaye/ClimaSen.git
cd ClimaSen
python3 -m venv venv
source venv/bin/activate                 # Windows : venv\Scripts\activate
pip install -r requirements.txt -r jarvis/requirements.txt

# Optionnel
pip install -r requirements-scripts.txt  # scripts géographiques et veille C3S
python -m playwright install chromium    # export PDF des rapports d'Iris
```

| Fichier | Contenu |
|---|---|
| `requirements.txt` | plateforme et calculs (Streamlit, Plotly, pandas, numpy, scipy, scikit-learn, xarray, netCDF4, h5py, matplotlib, shapely…) |
| `jarvis/requirements.txt` | Iris, API ouverte, rapports, tests (FastAPI, Uvicorn, Pydantic, SDK Anthropic, Jinja2, python-docx, Playwright, pytest…) |
| `requirements-scripts.txt` | geopandas, pyproj, pyshp, cdsapi, cartopy : scripts 14, 16, 20-22, 26-28, 34 seulement ; sans eux la plateforme fonctionne (cartes haute résolution sans cartopy, veille sans C3S) |

## 3. Configuration

```bash
cp .env.example .env
```

Toutes les variables sont décrites dans `.env.example`. **Aucun secret n'est fourni
dans ce dépôt.**

| Variable | Rôle | Sans elle |
|---|---|---|
| `ANTHROPIC_API_KEY` | conversation avec Iris (modèles Claude, payant à l'usage) | Iris démarre en mode « dégradé » : pas de chat, le reste fonctionne |
| `JARVIS_SECRET_KEY` | signature des sessions d'Iris : `python -c "import secrets; print(secrets.token_urlsafe(48))"` | clé éphémère tolérée en `JARVIS_ENV=dev` |
| `JARVIS_ENV` | `dev` en local, `prod` sur un serveur (secrets obligatoires) | `dev` |
| `JARVIS_ADMIN_PASSWORD_HASH` | profil administrateur (boutons d'exécution du pipeline, outils d'Iris réservés) : `python -m jarvis.auth` | profil administrateur fermé |
| `CDSAPI_KEY` | prévisions saisonnières Copernicus C3S de la veille | bulletin produit sans niveau de risque C3S |

## 4. Lancement

```bash
# Terminal 1 : plateforme              -> http://localhost:8501
streamlit run scripts/dashboard.py

# Terminal 2 : Iris + API ouverte
uvicorn jarvis.app:create_app --factory --port 8010
#   santé        http://localhost:8010/jarvis/health
#   API ouverte  http://localhost:8010/api/v1/   (documentation : /api/v1/docs)
```

La bulle d'Iris apparaît en bas de la plateforme 10 à 25 secondes après l'ouverture
de la page (dernier élément chargé). Après une modification du code, redémarrer
Streamlit **et** Uvicorn.

Production (nginx, systemd, HTTPS) : `deploy/setup_server.sh`,
`deploy/climatsen.service`, `deploy/jarvis.service`, `deploy/nginx-climatsen.conf`.

## 5. Données

**Incluses dans le dépôt, rien à télécharger pour utiliser la plateforme :** les 1 317
événements de pluie extrême et les grilles CHIRPS du Sénégal (1981-2023), les 11
indices SST, les résultats des téléconnexions et du clustering, l'indice de risque
(46 départements, 125 arrondissements), les données de l'ANSD (RGPH-5, EHCVM,
projections, Open Data Platform), les contours OCHA, les inondations documentées
2005-2020 et les prévisions Copernicus C3S. Sources détaillées :
`data/raw/SOURCES_ANSD_HDX.md`.

**Optionnelles, hors dépôt (trop volumineuses pour GitHub) :** nécessaires seulement
pour **relancer les calculs** et pour deux fonctions avancées d'Iris (état de
l'océan d'un jour précis, animation de n'importe quel événement).

| Donnée | Taille | Comment l'obtenir |
|---|---|---|
| SST journalière NOAA OISST v2, 1983-2023 | 42 Go | `python scripts/download_sst_noaa.py`, ou page Pipeline > Données SST |
| CHIRPS Afrique de l'Ouest (`data/raw/chirps_WA_1981_2023_dayly.mat`) | 290 Mo | sur demande à l'équipe |
| Cube SST mensuel (`data/processed/sst_cube_1deg.npz`) | 80 Mo | reconstruit à partir d'OISST : page Pipeline > Données SST > « Reconstruire le cube » |

`python scripts/39_verifier_sources.py` vérifie qu'une copie de ces fichiers est
identique à celle qui a produit nos résultats (tailles et empreintes SHA-256,
référence `outputs/sources_reference.json`).

## 6. Tests

```bash
python -m pytest tests/ -q      # ~1 430 tests, 7 à 13 min, sans appel payant (modèle simulé)
                                # 11 sont ignorés (skipped) si les données brutes optionnelles
                                # (OISST, CHIRPS Afrique de l'Ouest) sont absentes : c'est normal
python -m pytest tests/test_jarvis_page_context.py tests/test_rapports_figures.py -q   # < 1 min
```

Vérifications manuelles :

- `GET http://localhost:8010/jarvis/health` : `"status":"ok"` avec une clé
  Anthropic, `"degraded"` sans clé ;
- `GET http://localhost:8010/api/v1/donnees/departements?format=csv` : les 46
  départements ;
- optionnel, avec une clé : `python scripts/18_banc_epreuve_jarvis.py` pose 42
  questions au vrai modèle et note les réponses (quelques centimes).

## 7. Services externes

| Service | Usage | Obligatoire |
|---|---|---|
| API Anthropic (Claude) | conversation avec Iris | pour le chat seulement |
| Fonds de carte CARTO | fond des cartes de la plateforme | pour l'affichage des fonds (les données s'affichent sans) |
| Microsoft Edge TTS | voix d'Iris | non (repli sur la voix du navigateur) |
| NOAA PSL, CHC (UCSB) | téléchargement OISST et CHIRPS | non (recalcul seulement) |
| Copernicus CDS | prévisions C3S de la veille | non |
| ANSD Open Data Platform (SDMX) | synchronisation des données de l'ANSD (script 38) | non (copie incluse) |

## 8. Pipeline de calcul

Page Pipeline (profil administrateur) : chaque étape a son bouton ; « Lancer le
pipeline complet » enchaîne 18 étapes **en arrière-plan** (détection 01 à 14, veille
19-20, vulnérabilité 26-29, exposition 33-37, manifeste 32) et s'arrête à la première
erreur. L'état et le journal sont dans `outputs/taches/`.

## 9. Problèmes connus

- Python 3.11 ou plus ancien : erreur de syntaxe au lancement (voir Prérequis).
- Windows, dossier d'installation profond : `git clone` échoue avec « Filename too
  long » (voir Prérequis : chemin court ou `core.longpaths`).
- Sans `ANTHROPIC_API_KEY`, ou sans crédit sur le compte Anthropic, le chat d'Iris
  répond par une erreur ; le reste de la plateforme fonctionne.
- L'export PDF des rapports exige Chromium (`python -m playwright install chromium`) ;
  à défaut, Word et HTML restent disponibles.
- Les fonctions avancées de la veille (scénarios, mise à jour mensuelle) demandent le
  cube SST mensuel, absent du dépôt (voir Données).
- Le premier affichage de certaines pages prend quelques secondes (chargement des
  grilles en cache).

## 10. Documentation détaillée

| Sujet | Fichier |
|---|---|
| Iris : architecture, outils, sécurité | `jarvis/README.md` |
| API ouverte et SDMX | `donnees_ouvertes/README.md` |
| Sources ANSD et HDX | `data/raw/SOURCES_ANSD_HDX.md` |
| Charte graphique | `assets/branding/README.md` |
