# Hackathon Mobilités 2025 — Défi 4
## Améliorer l'accessibilité et le confort dans les services de mobilités

---

## 1. Concept du projet

### Problème
Les calculateurs d'itinéraire actuels (IDFM, SNCF Connect, Google Maps) optimisent sur le temps ou le nombre de correspondances. **La dimension confort n'existe pas.** Un voyageur ne sait pas, avant de partir :
- Si l'ascenseur de sa correspondance fonctionne
- Si sa rame va être bondée à cette heure
- Si la qualité de l'air est dégradée sur son trajet

### Solution
Un **moteur de recommandation d'itinéraire enrichi** qui ajoute une couche de confort par-dessus les itinéraires existants de l'API IDFM.

Pour chaque option d'itinéraire proposée, le système affiche **toujours** les 4 dimensions de confort :
- 👥 Affluence (niveau de fréquentation à l'heure choisie)
- 🌡️ Climatisation (matériel roulant des lignes empruntées)
- ♿ Accessibilité (statut des ascenseurs en temps réel)
- 🚻 Équipements (toilettes et fontaines à eau disponibles)

Et un **score de confort universel** (0–10) pour comparer les options entre elles.

### Ce qui nous différencie
- Pas de profil utilisateur à créer — zéro friction
- Toutes les dimensions toujours visibles — l'usager voit l'état complet d'un coup d'œil
- Score **dynamique** : ajusté selon le flux d'utilisateurs qui choisissent le même itinéraire (évite l'effet "tout le monde sur le même trajet")

---

## 2. Ce que voit l'utilisateur

Les 4 dimensions sont **toujours affichées** pour chaque itinéraire — pas seulement quand c'est problématique. L'utilisateur voit l'état complet d'un seul coup d'œil.

```
Paris Vincennes → La Défense   8h30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 1 — RER A direct          28 min
  👥 Très chargé   🌡️ Pas de clim   ⚠️ Ascenseur en panne à Auber   🚻 Toilettes dispo
  Score confort : 4/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 2 — Ligne 1              34 min    ✅ Recommandé
  👥 Chargé        🌡️ Climatisé     ✅ Accessible                    🚻 Pas de toilettes
  Score confort : 7/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 3 — Ligne 9 + RER A      41 min
  👥 Peu de monde  🌡️ Pas de clim   ✅ Accessible                    🚻 Toilettes dispo
  Score confort : 6/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Filtrer :  ☐ Ascenseurs  ☐ Peu de monde  ☐ Climatisé
```

---

## 3. Architecture technique

### Vue d'ensemble

```
Utilisateur
    │
    ▼
[Saisit : départ + destination + heure]
    │
    ▼
[Backend] Appel API IDFM /journeys
          (equipment_details=true, data_freshness=realtime, count=3)
    │
    │  La réponse contient déjà :
    │  ├─ sections type "transfer"     → durée + distance correspondance
    │  ├─ equipment_availability       → statut ascenseurs en temps réel
    │  └─ disruptions                  → perturbations actives
    │
    ▼
[Backend] Enrichissement complémentaire
    │  ├─ Lookup affluence (modèle synthétique horaire × station)
    │  └─ Lookup équipements (toilettes RATP)
    │
    ▼
[Backend] Génère les alertes + calcule le score
    │
    ▼
[Frontend] Affiche les options enrichies
```

### Structure du code

```
frontend/
  └── search/        → formulaire départ/arrivée/heure
  └── results/       → liste des itinéraires enrichis
  └── filters/       → filtres optionnels (sans compte)

backend/
  └── api.py         → endpoint POST /itineraries (FastAPI, CORS, filtres, charge dynamique)
  └── enricher.py    → enrichissement : 5 dimensions + météo + score ML
  └── test_api.py    → script de test CLI contre l'API IDFM

data/
  └── affluence.json           → patterns horaires × station (données d'entraînement ML)
  └── climatisation.json       → matériel roulant connu par ligne
  └── sanitaires-*.json        → toilettes RATP
  └── fontaines-*.json         → fontaines à eau RATP
  └── stations_aeriennes.json  → 30 stations aériennes (OSM + compléments M6)

models/
  └── affluence_model.pkl      → RandomForest entraîné sur les patterns horaires

scripts/
  └── train_affluence.py       → entraîne et sauvegarde le modèle affluence

tests/
  └── test_business_integration.py
  └── test_edge_cases.py
```

### Appel API principal

> ✅ **Validé le 2026-06-24** — Script `src/test_api.py` fonctionnel. Test Vincennes → La Défense à 8h30 : 3 itinéraires retournés (RER A ×2 en 20 min, Ligne 1 en 44 min). Format de réponse conforme aux attentes. IDs IDFM récupérés dynamiquement via `/places`.

```http
GET https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/journeys
Headers:
  apikey: VOTRE_CLE_API

Paramètres:
  from             = IDFM:stop_area:XXX   (ID station départ)
  to               = IDFM:stop_area:YYY   (ID station arrivée)
  datetime         = 20250624T083000      (date + heure)
  data_freshness   = realtime             (inclut les perturbations)
  equipment_details= true                 (statut ascenseurs dans la réponse)
  count            = 3                    (nombre d'itinéraires retournés)
```

### Structure de la réponse utilisée

```json
{
  "journeys": [
    {
      "duration": 1680,
      "sections": [
        {
          "type": "public_transport",
          "display_informations": { "commercial_mode": "Métro", "label": "1" }
        },
        {
          "type": "transfer",
          "duration": 240,        ← temps de correspondance (secondes)
          "geojson": { ... }      ← distance calculable depuis la géométrie
        },
        {
          "type": "public_transport",
          "stop_date_times": [
            {
              "equipment_availability": {
                "wheelchair_boarding": "available",  ← accessibilité PMR
                "elevator": "available"              ← statut ascenseur ⭐
              }
            }
          ]
        }
      ],
      "disruptions": [ ... ]     ← perturbations actives sur ce trajet
    }
  ]
}
```

### Endpoints secondaires

| Endpoint | Usage |
|---|---|
| `/equipment_reports` | Vérification ciblée d'un équipement sur une station spécifique |
| `/traffic_reports` | Perturbations actives sur l'ensemble du réseau |
| `/places?q=...` | Recherche d'une station par nom pour obtenir son ID IDFM |

---

## 4. Données utilisées (Défi 4)

| N° | Jeu de données | Dimension couverte | Accès |
|---|---|---|---|
| 19 | ~~Donnée Métro-connexion~~ | ~~Facilité de correspondance~~ | ~~Retiré~~ |
| 20 | Accessibilité en gare | Accessibilité | Public |
| 21 | Référentiel des arrêts | Correspondances | Public |
| 22 | ~~État des ascenseurs~~ | ~~Accessibilité~~ | ~~Remplacé par API~~ |
| 23 | Schéma directeur accessibilité | Accessibilité | Public |
| 24 | ~~Qualité de l'air réseau francilien~~ | ~~Qualité de l'air~~ | ~~Retiré~~ |
| 25 | Indicateurs qualité de service SNCF/RATP | Validation du score | Public |
| 26 | Positionnement dans la rame | Correspondances | Public |
| 27 | Toilettes publiques RATP | Équipements | Public |
| — | Fontaines à eau réseau RATP | Équipements | Public (CSV) |
| — | **Données synthétiques d'affluence** | **Affluence** | **Généré** |
| — | **Données synthétiques climatisation** | **Confort thermique** | **Généré** |

> **Note affluence :** Le dataset SNCF de comptages voyageurs est restreint aux participants enregistrés au hackathon. En remplacement, l'affluence est simulée via un modèle synthétique basé sur des patterns horaires connus (voir section 5). En production, ce module se branche directement sur les données de validation IDFM (maille horaire).

> **Note correspondance :** Le dataset Métro-connexion (n°19) est un site collaboratif HTML, pas un dataset exploitable. La dimension correspondance est extraite directement de la réponse de l'**API IDFM Calculateur générique v2 (Navitia)** — chaque itinéraire retourne des sections de type `transfer` contenant la durée et la distance de marche entre deux lignes. Aucun dataset supplémentaire n'est nécessaire.

> **Note ascenseurs :** Le dataset n°22 (État des ascenseurs) est remplacé par le paramètre `equipment_details=true` dans l'appel `/journeys`. La réponse API retourne directement le statut de chaque ascenseur sur le trajet en temps réel via le champ `equipment_availability`. Un dataset de moins à maintenir.

> **Note fontaines :** Dataset CSV trouvé localement (81 lignes). Couvre Métro 1–14 + RER A uniquement — pas de RER B/C/D/E ni Transilien. 74 fontaines en zone libre, 7 en zone contrôlée. L'`id IDM de l'accès le plus proche` est complet (0 valeurs manquantes) → jointure directe avec la réponse API IDFM possible. Couverture très partielle : la majorité des stations n'a pas de fontaine, ce qui est une information en soi (alerte 🚰 si aucune fontaine sur le trajet).

> **Note climatisation :** Dataset non trouvé en open data public (absent de l'Airtable hackathon pour les non-participants). Remplacé par un fichier synthétique basé sur les faits connus sur le matériel roulant RATP/SNCF.

> **Note qualité de l'air :** Le dataset n°24 a été retiré après audit — il ne contient que des stations aériennes (en plein air) et ne couvre pas les stations souterraines où la qualité de l'air est réellement un enjeu. Intégrer ce dataset aurait produit des scores non fondés. **En V2**, cette dimension pourra être ajoutée via les capteurs SQUALES RATP (mesures horaires réelles sur 6 stations souterraines) une fois généralisés à l'ensemble du réseau.

---

## 5. Logique de scoring

### Les 4 dimensions — toujours affichées

Toutes les dimensions sont affichées pour chaque itinéraire, quel que soit leur état. L'utilisateur voit l'état complet, pas seulement les problèmes.

| Dimension | Source | Icône | Implémentation |
|---|---|---|---|
| Affluence | `models/affluence_model.pkl` — RandomForest entraîné | 👥 | `_score_affluence()` |
| Climatisation | `climatisation.json` — matériel roulant connu | 🌡️ | `_score_climatisation()` |
| Accessibilité | API IDFM — `equipment_availability` en temps réel | ♿ | `_score_accessibilite()` |
| Équipements | `sanitaires.json` + `fontaines.json` | 🚻 | `_score_equipements()` |
| Correspondances | API IDFM — sections `transfer` | 🚶 | `_score_correspondances()` |
| Météo | Open-Meteo API (sans clé) + `stations_aeriennes.json` | 🌧️ | `_score_meteo()` |

> **Note climatisation :** affichée à titre informatif. Elle n'entre pas dans le calcul du score.

> **Note météo :** ajuste le score si pluie sur tronçon aérien (−1 pt) ou canicule (−0.5 pt). Alertes : "Pluie sur tronçons aériens", "Canicule : préférez une ligne climatisée", "Chaleur : vérifiez la climatisation".

### Formule du score universel

```
score = (affluence      × 0.35)
      + (accessibilité  × 0.30)
      + (correspondance × 0.20)
      + (équipements    × 0.15)
```

4 dimensions retenues — la qualité de l'air a été retirée faute de données souterraines fiables.
Chaque dimension est normalisée sur 0–10 avant application des poids.

### Modèle ML d'affluence (RandomForest)

L'affluence est prédite par un **RandomForestRegressor (scikit-learn)** entraîné sur 12 600 échantillons synthétiques générés depuis les patterns horaires connus.

**Features du modèle :**

| Feature | Type | Description |
|---|---|---|
| `heure` | int 0–23 | Heure de départ |
| `jour_semaine` | int 0–6 | 0=lundi, 6=dimanche |
| `is_weekend` | bool | Week-end = patterns de pointe plus doux |
| `poids_station` | int 1–3 | 1=standard, 2=gare importante, 3=grande gare |

**Performances (cross-validation 5 folds) :** MAE ≈ 1.39/10

```
# Prédictions types (modèle entraîné)
Nuit (2h, lundi, poids 1)          → score=9.85  niveau=VERY_LOW
Pointe matin (8h, lundi, poids 1)  → score=1.08  niveau=VERY_HIGH
Châtelet à 8h (poids 3)            → score=0.62  niveau=VERY_HIGH
Week-end 8h (poids 1)              → score=1.47  niveau=VERY_HIGH (moins intense)
Milieu de journée (14h)            → score=5.98  niveau=MEDIUM
```

Le modèle lisse les transitions entre créneaux (pas de saut brutal à 7h pile) et modélise correctement la différence semaine/week-end.

Pour réentraîner : `python scripts/train_affluence.py`

**En production**, les features seront remplacées par les données de validation IDFM (maille horaire) — le modèle se rebranché sur données réelles sans changer le reste du pipeline.

### Climatisation — dataset synthétique

Dataset non disponible en open data. Fichier synthétique basé sur le matériel roulant connu :

```python
CLIMATISATION = {
    # Métro — totalement climatisé
    "Métro 1":  "total",   # MP05
    "Métro 14": "total",   # MP14

    # Métro — partiellement climatisé (déploiement en cours)
    "Métro 4":  "partiel", # MP14 en déploiement
    "Métro 11": "partiel",

    # Métro — non climatisé (matériel ancien)
    "Métro 2":  "aucune",
    "Métro 3":  "aucune",
    "Métro 5":  "aucune",
    "Métro 6":  "aucune",
    "Métro 7":  "aucune",
    "Métro 8":  "aucune",
    "Métro 9":  "aucune",
    "Métro 10": "aucune",
    "Métro 12": "aucune",
    "Métro 13": "aucune",

    # RER
    "RER A": "partiel",  # MI09 climatisés, MI2N non
    "RER B": "partiel",  # MI79/MI84 non climatisés, Z50000 climatisés
    "RER C": "partiel",
    "RER D": "partiel",
    "RER E": "total",    # NAT, matériel récent
}

SCORE_CLIM = { "total": 10, "partiel": 6, "aucune": 2 }
```

Seuil d'alerte : `"aucune"` → 🌡️ *Pas de climatisation sur cette ligne*

### Fontaines à eau RATP — audit du dataset

- **81 fontaines**, format CSV, coordonnées GPS complètes
- Couvre **Métro 1–14 + RER A** uniquement (pas RER B/C/D/E, pas Transilien)
- `id IDM de l'accès le plus proche` : 0 valeurs manquantes → jointure API directe
- 74 fontaines en zone libre, 7 en zone contrôlée
- Couverture très partielle : absence de fontaine = information utile en soi

Seuil d'alerte : aucune fontaine sur tout le trajet → 🚰 *Pas d'eau potable disponible*

### Qualité de l'air — dimension retirée

Dataset audité et écarté : il ne contient que des stations aériennes (en plein air). Les stations souterraines — là où la qualité de l'air est réellement problématique — ne sont pas couvertes. Inclure ce dataset aurait produit des scores sans fondement.

**En V2 :** branchement sur les capteurs SQUALES RATP dès qu'ils couvrent suffisamment de stations souterraines.

### Score dynamique (différenciateur clé)

Si plusieurs utilisateurs choisissent le même itinéraire simultanément, le score d'affluence est ajusté à la baisse pour refléter la charge anticipée. Cela distribue naturellement les voyageurs sur les alternatives disponibles.

```
score_affiché = score_actuel - impact(utilisateurs_sur_ce_trajet)
```

---

## 6. Roadmap 5 jours

### ✅ Jour 1 — Exploration & cadrage technique

| Qui | Mission | Statut |
|---|---|---|
| Backend | Appel API IDFM `/journeys` fonctionnel (`src/test_api.py`) | ✅ |
| Data | Audit des datasets disponibles (Airtable hackathon, open data) | ✅ |
| Data | Identification des datasets exploitables vs inaccessibles | ✅ |
| Équipe | Cadrage technique : dimensions, score, architecture | ✅ |

**Livrable :** Script `test_api.py` validé — 3 itinéraires retournés avec équipements et perturbations.

---

### ✅ Jour 2 — Construction de la couche data

| Qui | Mission | Statut |
|---|---|---|
| Data | Dataset synthétique affluence (`data/affluence.json`) | ✅ |
| Data | Dataset synthétique climatisation (`data/climatisation.json`) | ✅ |
| Data | Intégration fontaines à eau (`data/fontaines-a-eau-dans-le-reseau-ratp.json`) | ✅ |
| Data | Intégration toilettes RATP (`data/sanitaires-reseau-ratp.json`) | ✅ |
| Backend | Pipeline d'enrichissement complet (`src/enricher.py`) | ✅ |
| Backend | Calcul du score de confort pondéré intégré dans l'enricher | ✅ |

**Livrable :** `enricher.py` testé — pour Vincennes → La Défense à 8h30 : 3 itinéraires enrichis avec les 4 dimensions et un score 5.8/10.

---

### ✅ Jour 3 — Intégration bout en bout

> **Frontend pris en charge par Claude Design** — l'équipe se concentre sur le backend et la qualité des données.

| Qui | Mission | Statut |
|---|---|---|
| Backend | Créer l'endpoint `POST /itineraries` (FastAPI) qui orchestre API IDFM + enricher | ✅ |
| Backend | CORS activé + `requirements.txt` créé | ✅ |
| Data/ML | Tester l'enricher sur 10+ trajets variés, relever les anomalies | ✅ |
| Data/ML | Documenter le format JSON de sortie de l'enricher | ✅ |

**Livrable :** Endpoint `POST /itineraries` fonctionnel en local (`src/api.py`). Réponse JSON enrichie documentée ci-dessous.

---

#### Lancer le serveur

```bash
cd src
python -m uvicorn api:app --reload --port 8000
```

Interface de test interactive disponible sur `http://localhost:8000/docs`.

> ⚠️ Utiliser l'année courante dans le champ `datetime` — l'API IDFM rejette les dates passées.

---

#### Format de la requête

```http
POST /itineraries
Content-Type: application/json

{
  "depart":   "Vincennes",
  "arrivee":  "La Défense",
  "datetime": "20260625T083000"
}
```

#### Format de la réponse

```json
{
  "depart":   "Vincennes",
  "arrivee":  "La Défense",
  "datetime": "20260625T083000",
  "itineraires": [
    {
      "duree_min": 28,
      "nb_correspondances": 0,
      "lignes": ["A"],
      "perturbations": [],
      "dimensions": {
        "affluence": {
          "niveau": "VERY_HIGH",
          "label": "Très chargé",
          "poids_station": 3,
          "score": 0.6
        },
        "climatisation": {
          "status": "partiel",
          "label": "Partiellement climatisé",
          "lignes": [{ "ligne": "A", "clim": "partiel", "score": 6 }],
          "score": 6
        },
        "accessibilite": {
          "ok": true,
          "pannes": [],
          "nb_checked": 12,
          "score": 10
        },
        "correspondances": {
          "nb": 0,
          "max_duree_sec": 0,
          "details": [],
          "score": 10
        },
        "equipements": {
          "toilettes": false,
          "fontaines": false,
          "score": 2
        }
      },
      "score_confort": 5.8
    }
  ]
}
```

**Formule du score :** `affluence×0.35 + accessibilité×0.30 + correspondances×0.20 + équipements×0.15`

---

### ✅ Jour 4 — Finition & charge dynamique

> **Frontend intégré par Claude Design** à partir du JSON de l'endpoint.

| Qui | Mission | Statut |
|---|---|---|
| Backend | Filtres query params : `?accessible=true&peu_de_monde=true&climatise=true` | ✅ |
| Backend | Logique de charge dynamique (score ajusté si plusieurs users choisissent le même trajet) | ✅ |
| Data/ML | Tester sur trajets edge cases (nuit, RER longue distance, grande gare) | ✅ |
| Data/ML | Préparer les chiffres pour le pitch (couverture datasets, nb stations) | ✅ |
| Data/ML | Intégration météo (Open-Meteo, sans clé) + `data/stations_aeriennes.json` (30 stations OSM) | ✅ |
| Data/ML | RandomForest affluence : entraîné sur 12 600 échantillons, MAE 1.39, feature jour_semaine | ✅ |

**Livrable :** Filtres et charge dynamique intégrés dans `src/api.py`. 22 tests edge cases passants (`tests/test_edge_cases.py`). Dimension météo active (34°C détectés aujourd'hui → alerte "Chaleur : vérifiez la climatisation").

#### Filtres query params

```http
POST /itineraries?accessible=true&peu_de_monde=true&climatise=true
```

| Paramètre | Effet |
|---|---|
| `accessible=true` | Exclut les itinéraires avec un ascenseur en panne |
| `peu_de_monde=true` | Garde uniquement les niveaux d'affluence LOW et VERY_LOW |
| `climatise=true` | Exclut les itinéraires sans aucune climatisation |

Les filtres sont combinables. La réponse inclut le champ `filtres` qui rappelle les paramètres actifs.

#### Charge dynamique

Quand un utilisateur choisit un itinéraire, il appelle :

```http
POST /itineraries/select
Content-Type: application/json

{
  "dep_id":   "stop_area:IDFM:71651",
  "arr_id":   "stop_area:IDFM:71517",
  "lignes":   ["A"],
  "datetime": "20260625T083000"
}
```

Le score d'affluence est ajusté lors des prochains appels à `/itineraries` :

```
malus = min(3.0, nb_utilisateurs_actifs × 0.5)
score_affluence_affiché = score_affluence - malus
```

Les compteurs expirent après **30 minutes** d'inactivité. Le champ `charge_dynamique` dans la réponse indique le nombre d'utilisateurs actifs sur cet itinéraire.

---

### 🔲 Jour 5 — Pitch

| Qui | Mission |
|---|---|
| Tout le monde | Tests finaux, bugs critiques |
| Data/ML | Slides data : sources, méthode, limites |
| Backend + Frontend | Stabiliser pour la démo live |
| Design/UX | Storytelling visuel du pitch |
| Tout le monde | Répétition du pitch (5–10 min) |

**Livrable :** Démo live + pitch convaincant.

---

## 7. Modèle économique

### Client principal : IDFM et les opérateurs (B2G)

IDFM et les opérateurs (RATP, SNCF) ont des budgets pour améliorer l'expérience voyageur et cherchent des briques technologiques à intégrer dans leurs apps existantes plutôt que de les construire eux-mêmes.

**Ce qu'on leur vend :** l'algorithme d'enrichissement + la couche d'alertes, intégrable dans SNCF Connect, Bonjour RATP, idfm.fr.

```
Contrat de licence → 50k–200k€/an
```

### API vendue aux apps de navigation (B2B SaaS)

Citymapper, Moovit, Google Maps achètent déjà des données de transport enrichies. Notre API ajoute une couche absente du marché : score de confort + alertes en temps réel.

```
Facturation à la requête ou abonnement mensuel
1000 requêtes/jour × 0,01€ = ~300€/mois par partenaire
→ scalable avec le nombre d'acteurs
```

### Outil mobilité pour les entreprises (B2B)

Les entreprises ont une obligation de déclarer l'empreinte carbone des trajets domicile-travail (CSRD). Un outil qui favorise le report modal vers les transports en commun a une valeur RH et RSE directe.

```
Abonnement entreprise → 2–5€/salarié/mois
```

### Valeur économique de la charge dynamique

Si le système redistribue 10% des voyageurs aux heures de pointe vers des alternatives, cela réduit les incidents liés à la surcharge et améliore la régularité. Ce bénéfice est **quantifiable en euros** pour IDFM — c'est l'argument central du pitch business.

---

## 8. Chiffres pour le pitch

### Couverture des datasets

| Dataset | Entrées | Stations uniques | Lignes couvertes |
|---|---|---|---|
| Fontaines à eau RATP | 81 | 81 | M1–14 + RER A (15 lignes) |
| Toilettes RATP | 48 | 41 | M1, 5, 6, 7, 10, 12, 13, 14 + RER A, B (10 lignes) |
| Climatisation | 30 lignes | — | M1–14 + RER A–E + Transilien H/J/K/L/N/P/R + T3a/b |
| Affluence (synthétique) | 9 créneaux horaires | 20 stations pondérées | Toutes lignes |

### Répartition climatisation réseau RATP/SNCF

| Statut | Lignes | % du réseau couvert |
|---|---|---|
| Totalement climatisé | M1, M14, RER E, Transilien H/J/K/L/N/P/R, T3a/b | 12 lignes |
| Partiellement climatisé | M4, M11, RER A/B/C/D | 6 lignes |
| Non climatisé | M2, M3, M5, M6, M7, M8, M9, M10, M12, M13 | 12 lignes |

> **Pour le pitch :** 40 % des lignes Métro/RER sont sans climatisation — c'est l'information que l'usager n'a nulle part aujourd'hui.

### Fontaines à eau

- **74** en accès libre (zone non contrôlée)
- **7** en zone contrôlée (nécessite un titre de transport)
- Couverture partielle : la majorité des stations n'a pas de fontaine → l'**absence** est une information utile en soi

### Tests de robustesse

- **22 tests automatisés** couvrant les cas extrêmes : nuit, heure de pointe, grande gare, pannes multiples, correspondances longues, lignes inconnues, charge dynamique
- Tous les tests passent (`pytest tests/` → 22 passed)

---

## 9. Pitch en une phrase

> *"Nous avons enrichi le calculateur d'itinéraire IDFM avec une couche de confort en temps réel — pas un score abstrait, mais des alertes concrètes sur ce qui va vous poser problème, avec un système qui distribue intelligemment les voyageurs pour éviter que tout le monde converge vers le même trajet."*
