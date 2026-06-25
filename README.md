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

- [docs/hackathon_mobilites_defi4.md](docs/hackathon_mobilites_defi4.md) : contexte détaillé du projet et logique métier ;
- [src/enricher.py](src/enricher.py) : logique d'enrichissement des itinéraires et calcul du score de confort ;
- [src/test_api.py](src/test_api.py) : test d'appel à l'API IDFM et extraction des données utiles ;
- [data](data) : jeux de données locaux utilisés pour le confort et l'équipement.

## Utilisation rapide

1. Ajouter votre clé API IDFM dans un fichier .env sous la forme :
   `IDFM_API_KEY=votre_cle`
2. Installer les dépendances Python nécessaires :
   `pip install requests python-dotenv`
3. Lancer la vérification de l'API :
   `python src/test_api.py`
4. Lancer l'enrichissement des itinéraires :
   `python src/enricher.py`
