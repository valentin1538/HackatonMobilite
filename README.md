# HackatonMobilite — confort+

Projet Python développé dans le cadre du défi 4 du Hackathon Mobilités 2025 : améliorer l'accessibilité et le confort dans les services de mobilité en Île-de-France.

## Objectif

**confort+** est un moteur de recommandation d'itinéraires enrichis qui va au-delà du simple temps de trajet. Pour chaque option proposée par l'API IDFM/Navitia, il calcule un **score de confort global sur 10** en agrégeant six dimensions :

| Dimension | Poids | Source |
|---|---|---|
| **Affluence** | 35 % | Données IDFM 2023 (profils horaires réels) + modèle ML (fallback) |
| **Accessibilité** | 30 % | Statut temps réel des ascenseurs (API IDFM `equipment_details`) |
| **Correspondances** | 20 % | Nombre et durée des transferts |
| **Équipements** | 15 % | Toilettes et fontaines à eau (datasets RATP) |
| Climatisation | info | Statut par ligne (total / partiel / aucune) |
| Météo | info | Température, pluie, canicule via Open-Meteo (temps réel + prévisions J+16) |

Un résumé métier (recommandation, alertes, points forts) est généré pour chaque itinéraire.

## Architecture

```
┌──────────────┐      POST /itineraries       ┌──────────────────┐
│   Frontend   │ ───────────────────────────▶  │  API FastAPI     │
│  (static/)   │ ◀─────────────────────────── │  (src/api.py)    │
│  HTML/JS/CSS │      JSON enrichi            │                  │
└──────────────┘                               │  ┌────────────┐ │
       │  GET /stations                        │  │ enricher   │ │──▶ API IDFM/Navitia
       └──────────────────────────────────▶    │  │ (enrich()) │ │──▶ Open-Meteo
                                               │  └────────────┘ │
                                               │  ┌────────────┐ │
                                               │  │ historique │ │──▶ data/historique_trajets.csv
                                               │  └────────────┘ │
                                               └──────────────────┘
                                                       │
                                               ┌───────▼────────┐
                                               │  Modèles ML    │
                                               │  (models/*.pkl)│
                                               └────────────────┘
```

- **API FastAPI** (`src/api.py`) — expose les endpoints REST, applique les filtres confort (accessibilité, affluence, climatisation) et gère la **charge dynamique** (le score d'affluence baisse si trop d'utilisateurs choisissent le même itinéraire).
- **Enricher** (`src/enricher.py`) — interroge l'API IDFM, croise les données locales (affluence horaire, climatisation, fontaines, sanitaires, stations aériennes) et la météo Open-Meteo pour produire les 6 dimensions du score de confort.
- **Historique** (`src/historique.py`) — enregistre chaque trajet observé en temps réel dans un CSV pour permettre le ré-entraînement du modèle de confort.
- **Frontend** (`static/`) — interface web vanilla HTML/JS/CSS avec autocomplétion des stations, sélection de l'heure, filtres confort, 3 vues (Sobre / Carte / Comparatif), et détail par itinéraire.

### Endpoints de l'API

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/itineraries` | Recherche d'itinéraires enrichis (filtres `accessible`, `peu_de_monde`, `climatise`) |
| `POST` | `/itineraries/select` | Signale le choix d'un itinéraire (ajuste le score en temps réel) |
| `GET` | `/stations?q=...` | Autocomplétion des noms de stations |

### Machine Learning

Deux modèles `RandomForestRegressor` (scikit-learn) sont entraînés :

- **Modèle d'affluence** (`scripts/train_affluence.py`) — prédit le score d'affluence à partir de l'heure, du jour et du type de station. Utilisé en fallback quand les données réelles IDFM manquent.
- **Modèle de confort** (`scripts/train_confort.py`) — prédit le score de confort global pour les trajets futurs, entraîné sur l'historique des trajets réellement observés. Activé automatiquement dès 50 trajets historiques.

Le script `scripts/seed_historique.py` permet de peupler rapidement l'historique en appelant l'API locale sur plusieurs paires de stations.

## Structure du dépôt

```
├── src/
│   ├── api.py              # API FastAPI (endpoints, filtres, charge dynamique)
│   ├── enricher.py          # Enrichissement des itinéraires (6 dimensions, score)
│   ├── historique.py        # Logging des trajets observés (CSV)
│   └── test_api.py          # Script de test d'appel à l'API IDFM
├── static/
│   ├── index.html           # Frontend web (point d'entrée)
│   ├── app.js               # Logique UI (autocomplétion, cartes, détails)
│   └── app.css              # Styles (animations, spinner)
├── scripts/
│   ├── train_affluence.py   # Entraînement du modèle d'affluence
│   ├── train_confort.py     # Entraînement du modèle de confort
│   └── seed_historique.py   # Peuplement de l'historique de trajets
├── models/
│   ├── affluence_model.pkl  # Modèle ML affluence (RandomForest)
│   └── confort_model.pkl    # Modèle ML confort (RandomForest)
├── data/
│   ├── affluence_horaire.json       # Profils d'affluence IDFM 2023
│   ├── affluence.json               # Créneaux horaires et poids stations
│   ├── climatisation.json           # Statut climatisation par ligne
│   ├── fontaines-a-eau-dans-le-reseau-ratp.json
│   ├── sanitaires-reseau-ratp.json
│   ├── stations_aeriennes.json      # Stations en plein air (impact météo)
│   ├── historique_trajets.csv       # Historique des trajets observés
│   └── IDFM_API.json               # Données brutes API IDFM
├── notebooks/
│   └── analyse_affluence_ml.ipynb   # Analyse exploratoire affluence
├── tests/                           # Tests unitaires (pytest)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Utilisation rapide

### 1. Clé API

Copier `.env.example` en `.env` et y coller votre clé API IDFM :

```
IDFM_API_KEY=votre_cle_ici
```

### 2. Installation

```bash
pip install -r requirements.txt
```

### 3. Lancer le serveur

```bash
cd src
python -m uvicorn api:app --reload
```

L'interface web est accessible sur [http://localhost:8000](http://localhost:8000).

### 4. (Optionnel) Entraîner les modèles ML

```bash
# Modèle d'affluence (données synthétiques)
python scripts/train_affluence.py

# Peupler l'historique de trajets (nécessite le serveur actif + clé API valide)
python scripts/seed_historique.py

# Modèle de confort (nécessite ≥ 50 trajets dans l'historique)
python scripts/train_confort.py
```

### 5. Lancer les tests

```bash
pytest tests/
```
