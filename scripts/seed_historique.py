"""
Peuple l'historique de trajets (data/historique_trajets.csv) en appelant
l'API locale sur plusieurs paires de stations réelles, à l'heure actuelle.

Prérequis :
    - l'API doit tourner en local : python -m uvicorn api:app --reload
    - IDFM_API_KEY doit être valide (l'API interroge le vrai planificateur IDFM)

Un trajet n'est loggé que s'il est demandé à moins d'1h de l'instant présent
(voir enricher.SEUIL_TEMPS_REEL_HEURES) — ce script ne peut donc pas simuler
plusieurs heures de la journée en une seule exécution. Chaque appel peut
logger jusqu'à 3 lignes (un par itinéraire proposé). Pour une vraie diversité
horaire/météo, relancez ce script à différents moments de la journée/semaine
plutôt qu'en une seule fois.

Usage :
    python scripts/seed_historique.py
"""

import sys
import time
from datetime import datetime

import requests

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://localhost:8000/itineraries"

# Paires de stations réelles, variées (grandes gares, stations classiques, aériennes)
TRAJETS = [
    ("Vincennes", "La Défense"),
    ("Châtelet - Les Halles", "Nation"),
    ("Gare du Nord", "Montparnasse"),
    ("Porte Maillot", "Bastille"),
    ("République", "Denfert-Rochereau"),
    ("Saint-Lazare", "Gare de Lyon"),
    ("Nation", "Étoile"),
    ("Bastille", "Châtelet - Les Halles"),
]


def main():
    total_itineraires = 0
    total_appels = 0

    for depart, arrivee in TRAJETS:
        dt = datetime.now().strftime("%Y%m%dT%H%M%S")
        try:
            r = requests.post(
                API_URL,
                json={"depart": depart, "arrivee": arrivee, "datetime": dt},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            n = len(data.get("itineraires", []))
            total_itineraires += n
            total_appels += 1
            print(f"  {depart} → {arrivee} : {n} itinéraire(s) loggé(s)")
        except Exception as e:
            print(f"  {depart} → {arrivee} : échec ({e})")

        time.sleep(0.5)  # ménage l'API IDFM

    print(f"\n{total_appels} appel(s) effectué(s), ~{total_itineraires} ligne(s) ajoutée(s) à l'historique.")
    print("Relancez ce script à d'autres moments pour diversifier les données, puis :")
    print("  python scripts/train_confort.py")


if __name__ == "__main__":
    main()
