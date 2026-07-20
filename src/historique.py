"""
Historique des trajets réellement observés (données temps réel), utilisé
pour ré-entraîner le modèle de prédiction du score de confort.

Chaque appel à l'API avec une date proche (aujourd'hui) enregistre une ligne
via log_trajet(). Le script scripts/train_confort.py relit cet historique
via lire_historique() pour (ré)entraîner le modèle ML.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
HISTORIQUE_PATH = DATA_DIR / "historique_trajets.csv"

# Nombre minimal de trajets historiques avant d'utiliser le modèle ML de confort
# (en dessous, le modèle serait surappris — on reste sur la formule de règles).
MIN_SAMPLES_CONFORT_MODEL = 50

# Ordre des features du modèle de confort — partagé entre l'entraînement
# (scripts/train_confort.py) et l'inférence (enricher._load_confort_model)
# pour qu'ils restent en phase.
CONFORT_FEATURES = [
    "heure",
    "jour_semaine",
    "is_weekend",
    "affluence_score",
    "climatisation_score",
    "equipements_score",
    "nb_correspondances",
    "meteo_temperature",
    "meteo_precipitation",
]

FIELDS = [
    "logged_at",
    "heure",
    "jour_semaine",
    "is_weekend",
    "station_dep",
    "station_arr",
    "lignes",
    "affluence_score",
    "climatisation_score",
    "accessibilite_score",
    "correspondances_score",
    "equipements_score",
    "nb_correspondances",
    "meteo_temperature",
    "meteo_precipitation",
    "score_confort",
]


def log_trajet(depart: str, arrivee: str, departure_dt: str, enrichi: dict) -> None:
    """Ajoute une ligne d'historique à partir d'un trajet réellement observé.

    À n'appeler que pour des trajets avec données temps réel authentiques
    (enrichi["donnee_temps_reel"] est True) — jamais sur une prédiction ML,
    pour éviter que le modèle ne s'entraîne sur ses propres sorties.
    """
    d = enrichi["dimensions"]
    heure = int(departure_dt[9:11])
    jour_semaine = datetime.strptime(departure_dt[:8], "%Y%m%d").weekday()

    row = {
        "logged_at":             datetime.now(timezone.utc).isoformat(),
        "heure":                 heure,
        "jour_semaine":          jour_semaine,
        "is_weekend":            int(jour_semaine >= 5),
        "station_dep":           depart,
        "station_arr":           arrivee,
        "lignes":                "|".join(enrichi.get("lignes", [])),
        "affluence_score":       d["affluence"]["score"],
        "climatisation_score":   d["climatisation"]["score"],
        "accessibilite_score":   d["accessibilite"]["score"],
        "correspondances_score": d["correspondances"]["score"],
        "equipements_score":     d["equipements"]["score"],
        "nb_correspondances":    d["correspondances"]["nb"],
        "meteo_temperature":     d["meteo"].get("temperature"),
        "meteo_precipitation":   d["meteo"].get("precipitation"),
        "score_confort":         enrichi["score_confort"],
    }

    DATA_DIR.mkdir(exist_ok=True)
    file_existe = HISTORIQUE_PATH.exists()
    with open(HISTORIQUE_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_existe:
            writer.writeheader()
        writer.writerow(row)


def lire_historique() -> list[dict]:
    """Relit l'historique des trajets pour l'entraînement. Liste vide si absent."""
    if not HISTORIQUE_PATH.exists():
        return []
    with open(HISTORIQUE_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
