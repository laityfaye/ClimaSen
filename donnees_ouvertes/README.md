# API ouverte de ClimatSen

Les statistiques produites par la plateforme, en lecture seule, sans compte ni clé :
**https://climatsen.innosft.com/api/v1/** (documentation interactive : `/api/v1/docs`).

| Jeu | Lignes | Contenu | Flux SDMX |
|---|---|---|---|
| `departements` | 46 | Indice de risque (aléa, exposition, vulnérabilité), population RGPH-5, pauvreté EHCVM | `DF_RISQUE_DEPARTEMENTS` |
| `arrondissements` | 125 | Même indice par arrondissement | `DF_RISQUE_ARRONDISSEMENTS` |
| `communes` | 552 | Population, ménages, densité, jours de pluie extrême | `DF_EXPOSITION_COMMUNES` |
| `evenements` | 1 317 | Journées de pluie extrême 1981-2023 et habitants de la zone touchée | `DF_EVENEMENTS` |
| `annees` | 43 | Agrégation annuelle des événements | `DF_EVENEMENTS_ANNUELS` |
| `evenements_recents` | 99 au 5 oct. 2026 | Saisons depuis 2024 (référence 1981-2023), habitants avec la population de l'année ; colonne `source` : CHIRPS définitif ou préliminaire | `DF_EVENEMENTS_RECENTS` |

Zones : **P-codes OCHA** (COD-AB 2024) pour le pays (`SN`), les régions (`SN07`), les
départements (`SN0703`) et les arrondissements (`SN070301`). Les communes n'ont pas de
P-code : leur identifiant est le P-code du département suivi du nom ANSD
(`SN0101_NGOR`), et leur **code ANSD** (`COD_ENTITE`) est donné à part. Ce code ne peut
pas servir d'identifiant, car il est partagé par deux communes de Podor dans le fichier
de l'ANSD.

## Exemples

```bash
# JSON, avec filtres
curl "https://climatsen.innosft.com/api/v1/donnees/departements?region=Kolda&indicateurs=POPULATION,INDICE_RISQUE"
curl "https://climatsen.innosft.com/api/v1/donnees/evenements?annee=2012&population_min=5000000&tri=population_touchee"
curl "https://climatsen.innosft.com/api/v1/evenements/2012-09-28"

# CSV
curl "https://climatsen.innosft.com/api/v1/donnees/communes?departement=SN0101&format=csv"

# SDMX (requêtes de l'API REST SDMX) : clé FREQ.REF_AREA.INDICATOR
curl "https://climatsen.innosft.com/api/v1/sdmx/data/DF_RISQUE_DEPARTEMENTS/A.SN0703+SN1204.INDICE_RISQUE?format=sdmx-csv"
curl "https://climatsen.innosft.com/api/v1/sdmx/data/CLIMATSEN,DF_EVENEMENTS,1.0/D.SN.POPULATION_TOUCHEE?startPeriod=2020"
curl -H "Accept: application/vnd.sdmx.data+csv;version=2.0.0" \
     "https://climatsen.innosft.com/api/v1/sdmx/data/DF_EVENEMENTS_ANNUELS"

# Structures SDMX (flux, structure de données, listes de codes, concepts)
curl "https://climatsen.innosft.com/api/v1/sdmx/structure"
curl "https://climatsen.innosft.com/api/v1/sdmx/codelist/CLIMATSEN/CL_ZONE/1.0"

# Contours avec indicateurs, à ouvrir directement dans QGIS
curl "https://climatsen.innosft.com/api/v1/geo/communes.geojson"
```

```python
import pandas as pd
base = "https://climatsen.innosft.com/api/v1"
deps = pd.read_csv(base + "/donnees/departements?format=csv")
obs = pd.read_csv(base + "/sdmx/data/DF_EXPOSITION_COMMUNES/A..POPULATION?format=sdmx-csv")
```

```r
deps <- read.csv("https://climatsen.innosft.com/api/v1/donnees/departements?format=csv")
```

Dans Excel : *Données > À partir du web*, avec l'adresse d'un export CSV.

## SDMX

Une seule structure de données (`CLIMATSEN:DSD_CLIMATSEN(1.0)`) sert les cinq flux :

| Composant | Rôle | Représentation |
|---|---|---|
| `FREQ` | dimension | `CL_FREQ` : A annuelle, D journalière |
| `REF_AREA` | dimension | `CL_ZONE` : 738 zones hiérarchisées (pays > région > département > arrondissement ou commune) |
| `INDICATOR` | dimension | `CL_INDICATEUR` : 29 indicateurs |
| `TIME_PERIOD` | dimension temporelle | `2023`, `2012-09-28`... |
| `OBS_VALUE` | mesure | nombre |
| `UNIT_MEASURE` | attribut d'observation | `CL_UNITE` |

* Formats : **SDMX-CSV 2.0** et **SDMX-JSON 2.0** (données), SDMX-JSON 2.0 (structures).
  Les messages SDMX-JSON ont été validés contre les schémas officiels v2.0.0
  (github.com/sdmx-twg/sdmx-json) : 5 flux de données et 5 requêtes de structure, sans
  erreur.
* Paramètres : `startPeriod`, `endPeriod`, `format` (`sdmx-csv`, `sdmx-json`) ou en-tête
  `Accept`, `labels=both` pour ajouter les libellés au CSV.
* Pour les indices et la population par zone, `TIME_PERIOD` vaut 2023, l'année de la
  population. L'aléa porte sur 1981-2023.
* L'agence `CLIMATSEN` maintient ces structures. Ce ne sont pas des structures
  officielles de l'ANSD : elles reprennent les concepts transversaux de la norme
  (`FREQ`, `REF_AREA`, `TIME_PERIOD`, `OBS_VALUE`, `UNIT_MEASURE`), pour qu'un outil
  SDMX les lise sans configuration.

## Règles

* **Lecture seule.** L'API ne recalcule rien : elle sert les fichiers produits par les
  scripts 26 à 34 (`outputs/`, `data/processed/`). Elle relit un fichier dès qu'il
  change.
* **Sources et limites dans chaque réponse.** L'indice de risque a une AUC de 0,49 sur
  les inondations documentées. « Population touchée » désigne les habitants de la zone
  de pluie extrême, pas un nombre de sinistrés. Les contours des communes sont
  reconstruits.
* **Licence** des données dérivées : CC BY 4.0, avec attribution de ClimatSen, de l'ANSD,
  d'OCHA et de CHIRPS (constante `LICENCE` dans `sources.py`).
* **Débit** : 120 requêtes en rafale par adresse, puis 2 par seconde (application),
  120 par minute (nginx, zone `api`). Une réponse 429 indique le délai dans
  `Retry-After`.
* **CORS** ouvert (`Access-Control-Allow-Origin: *`) : il n'y a ni cookie ni session.

## Déploiement

L'API tourne dans le processus d'IRIS : `jarvis/app.py` la monte sous `/api/v1` et lui
passe sa fonction de lecture de l'adresse client. `deploy/nginx-climatsen.conf`
contient la règle `location /api/` et la zone de débit `api`. Après la mise à jour du
serveur :

```bash
sudo cp deploy/nginx-climatsen.conf /etc/nginx/sites-available/climatsen
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl restart jarvis
```

Tests : `pytest tests/test_donnees_ouvertes.py` (32 tests sur les vrais fichiers publiés).
