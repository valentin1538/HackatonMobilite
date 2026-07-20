"""
Peuple rapidement l'historique de trajets (data/historique_trajets.csv) en
appelant l'API locale sur plusieurs paires de stations réelles, à l'heure
actuelle et à quelques heures différentes d'aujourd'hui.

Prérequis :
    - l'API doit tourner en local : python -m uvicorn api:app --reload
    - IDFM_API_KEY doit être valide (l'API interroge le vrai planificateur IDFM)

Chaque appel peut logger jusqu'à 3 lignes (un par itinéraire proposé), donc
une vingtaine d'appels suffit généralement pour atteindre les 50 lignes
nécessaires à l'entraînement de scripts/train_confort.py.

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

# Heures à essayer sur la journée en cours (toutes comptent comme "aujourd'hui")
HEURES = ["08", "12", "17", "20"]


def main():
    aujourd_hui = datetime.now().strftime("%Y%m%d")
    total_itineraires = 0
    total_appels = 0

    for depart, arrivee in TRAJETS:
        for heure in HEURES:
            dt = f"{aujourd_hui}T{heure}3000"
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
                print(f"  {depart} → {arrivee} à {heure}h : {n} itinéraire(s) loggé(s)")
            except Exception as e:
                print(f"  {depart} → {arrivee} à {heure}h : échec ({e})")

            time.sleep(0.5)  # ménage l'API IDFM

    print(f"\n{total_appels} appel(s) effectué(s), ~{total_itineraires} ligne(s) ajoutée(s) à l'historique.")
    print("Lancez maintenant : python scripts/train_confort.py")


if __name__ == "__main__":
    main()
