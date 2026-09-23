# HackatonMobilite

Projet Python développé dans le cadre du défi 4 du Hackathon Mobilités 2025 : améliorer l'accessibilité et le confort dans les services de mobilité.

## Objectif

Le projet propose un moteur de recommandation d'itinéraires enrichis qui va au-delà du simple temps de trajet. Pour chaque option, il affiche des informations de confort utiles à l'utilisateur :

- affluence estimée à l'heure choisie ;
- niveau de climatisation sur les lignes empruntées ;
- accessibilité réelle via les informations d'équipement de l'API IDFM ;
- présence de toilettes et de fontaines à eau ;
- qualité des correspondances.

Un score de confort global est ensuite calculé pour comparer les itinéraires entre eux.

## Architecture du projet

- l'API IDFM/Navitia est utilisée pour récupérer les itinéraires disponibles ;
- les données locales et synthétiques complètent les informations manquantes ;
- un enrichissement est appliqué à chaque trajet avant d'afficher un résultat interprétable.

## Structure du dépôt

- [src/api.py](src/api.py) : API FastAPI (endpoints itinéraires, stations) et service du frontend ;
- [src/enricher.py](src/enricher.py) : logique d'enrichissement des itinéraires et calcul du score de confort ;
- [src/historique.py](src/historique.py) : journalisation des trajets et modèle de prédiction du confort ;
- [src/test_api.py](src/test_api.py) : test d'appel à l'API IDFM et extraction des données utiles ;
- [static](static) : frontend (HTML/CSS/JS sans framework) servi par l'API ;
- [data](data) : jeux de données locaux utilisés pour le confort et l'équipement.

## Installation

1. Ajouter votre clé API IDFM dans un fichier `.env` à la racine :

   ```
   IDFM_API_KEY=votre_cle
   ```

2. Installer les dépendances :

   ```bash
   pip install -r requirements.txt
   ```

## Lancer l'application

Le frontend est servi directement par l'API : une seule commande suffit pour
avoir l'application complète.

```bash
uvicorn api:app --reload --app-dir src
```

- application web : http://127.0.0.1:8000
- documentation interactive de l'API : http://127.0.0.1:8000/docs

L'option `--app-dir src` est nécessaire : les modules de `src/` s'importent
entre eux à plat (`from enricher import ...`).

Pour changer de port :

```bash
uvicorn api:app --reload --app-dir src --port 8080
```

## Scripts en ligne de commande

Vérifier la connexion à l'API IDFM et afficher des itinéraires enrichis :

```bash
python -m src.test_api
```

Lancer la démo d'enrichissement des itinéraires :

```bash
python src/enricher.py
```

Lancer les tests :

```bash
pytest
```
