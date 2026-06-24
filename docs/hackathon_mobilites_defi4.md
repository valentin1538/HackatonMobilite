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

Pour chaque option d'itinéraire proposée, le système génère :
- Des **alertes spécifiques** sur ce qui va poser problème
- Un **score de confort universel** (0–10) pour comparer les options entre elles

### Ce qui nous différencie
- Pas de profil utilisateur à créer — zéro friction
- Les alertes remplacent la personnalisation : chaque usager voit ce qui le concerne naturellement
- Score **dynamique** : ajusté selon le flux d'utilisateurs qui choisissent le même itinéraire (évite l'effet "tout le monde sur le même trajet")

---

## 2. Ce que voit l'utilisateur

```
Paris Vincennes → La Défense   8h30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 1 — RER A direct          28 min
⚠️  Ascenseur en panne à Auber
👥  Très chargé à cette heure
Score confort : 4/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 2 — Ligne 1              34 min    ✅ Recommandé
👥  Chargé mais acceptable
Score confort : 7/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Option 3 — Ligne 9 + RER A      41 min
💨  Qualité de l'air dégradée ligne 4
Score confort : 6/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Filtrer :  ☐ Ascenseurs  ☐ Peu de monde  ☐ Air pur
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
  └── idfm_client    → appel API IDFM /journeys (equipment_details=true)
  └── enricher       → orchestration des lookups complémentaires
  └── scorer         → calcul du score par itinéraire
  └── alerter        → génération des alertes

data/
  └── ~~ascenseurs~~ → remplacé par equipment_details=true dans l'appel API
  └── ~~air~~        → dataset retiré (stations aériennes uniquement, non pertinent)
  └── affluence      → données synthétiques (modèle horaire × station)
  └── equipements    → toilettes RATP (seul fichier statique restant)
  └── correspondances → sections `transfer` de la réponse API IDFM (natif)
```

### Appel API principal

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

### Alertes par dimension

| Dimension | Source | Seuil | Icône |
|---|---|---|---|
| Accessibilité | État des ascenseurs | Ascenseur en panne sur le trajet | ⚠️ |
| Affluence | Données synthétiques (modèle horaire) | Créneau HIGH ou VERY_HIGH | 👥 |
| ~~Qualité de l'air~~ | ~~Dataset retiré (stations aériennes uniquement)~~ | — | — |
| Équipements | Toilettes RATP | Aucune toilette sur le trajet | 🚻 |
| Correspondance | API IDFM — sections `transfer` | Durée transfer > 5 min ou distance > 300m | 🚶 |

Pas d'alerte = dimension OK, rien affiché.

### Formule du score universel

```
score = (affluence      × 0.35)
      + (accessibilité  × 0.30)
      + (correspondance × 0.20)
      + (équipements    × 0.15)
```

4 dimensions retenues — la qualité de l'air a été retirée faute de données souterraines fiables.
Chaque dimension est normalisée sur 0–10 avant application des poids.

### Modèle synthétique d'affluence

Faute d'accès aux données de validation IDFM (restreintes aux participants du hackathon), l'affluence est générée via un modèle basé sur des patterns horaires connus :

```python
AFFLUENCE = {
    "VERY_HIGH": (7, 9),    # heure de pointe matin  → score 1/10
    "HIGH":      (16, 19),  # heure de pointe soir   → score 3/10
    "MEDIUM":    (9, 16),   # journée                → score 6/10
    "LOW":       (19, 22),  # soirée                 → score 8/10
    "VERY_LOW":  (22, 7),   # nuit                   → score 10/10
}
```

Ce score est ensuite pondéré par la fréquentation annuelle de la station (source : Fréquentation en gares SNCF, dataset public) pour distinguer une grande gare d'une station secondaire.

**En production**, ce module se branche sur les données de validation IDFM (maille horaire) pour un score basé sur des données réelles.

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

### Jour 1 — Exploration & cadrage technique

| Qui | Mission |
|---|---|
| Tout le monde | Lire les datasets, tester l'API IDFM playground |
| Data/ML | Ouvrir les 5 datasets, évaluer qualité et format |
| Backend | Faire un vrai appel API IDFM, comprendre la réponse |
| Design/UX | Première maquette basse fidélité (papier suffit) |
| Frontend | Préparer l'environnement technique |

**Livrable :** On sait ce que contient chaque dataset + un appel IDFM qui fonctionne

---

### Jour 2 — Construction de la couche data

| Qui | Mission |
|---|---|
| Data/ML | Nettoyer et normaliser les datasets, construire les tables de lookup par station |
| Data/ML | Définir les seuils d'alerte pour chaque dimension |
| Backend | Construire le pipeline d'enrichissement (itinéraire → lookups → alertes) |
| Design/UX | Maquette haute fidélité, valider avec l'équipe |
| Frontend | Formulaire de recherche fonctionnel |

**Livrable :** Pour une station donnée, on peut sortir ses alertes

---

### Jour 3 — Intégration bout en bout

| Qui | Mission |
|---|---|
| Data/ML | Implémenter le calcul du score universel |
| Backend | Brancher IDFM + enrichissement + score dans un endpoint unique |
| Frontend | Afficher les résultats enrichis (alertes + score par option) |
| Design/UX | Intégrer la charte visuelle dans le frontend |

**Livrable :** Un trajet réel de A à B retourne des options avec alertes et scores

---

### Jour 4 — Finition & charge dynamique

| Qui | Mission |
|---|---|
| Data/ML | Affiner les seuils, tester sur plusieurs trajets réels |
| Backend | Ajouter la logique de charge dynamique |
| Frontend | Ajouter les filtres optionnels (ascenseurs / peu de monde / air pur) |
| Design/UX | Polish UI, responsive |

**Livrable :** Produit complet et testable sur une démo

---

### Jour 5 — Pitch

| Qui | Mission |
|---|---|
| Tout le monde | Tester sur trajets variés, corriger les bugs critiques |
| Data/ML | Préparer les slides data : sources, méthode, limites |
| Backend + Frontend | Stabiliser pour la démo live |
| Design/UX | Storytelling visuel du pitch |
| Tout le monde | Répéter le pitch (5–10 min) |

**Livrable :** Démo live + pitch convaincant

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

## 8. Pitch en une phrase

> *"Nous avons enrichi le calculateur d'itinéraire IDFM avec une couche de confort en temps réel — pas un score abstrait, mais des alertes concrètes sur ce qui va vous poser problème, avec un système qui distribue intelligemment les voyageurs pour éviter que tout le monde converge vers le même trajet."*
