"""
Entraîne un RandomForestRegressor pour prédire le score d'affluence
à partir de : heure, jour_semaine, is_weekend, poids_station.

Les données d'entraînement sont générées synthétiquement depuis
les patterns horaires de data/affluence.json.

Usage :
    python scripts/train_affluence.py
"""

import sys
import json
import pickle
import numpy as np
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "affluence_model.pkl"


def _slot_score(heure: int, creneaux: list) -> float:
    for s in creneaux:
        if s["debut"] <= heure < s["fin"]:
            return float(s["score"])
    return 6.0


def _niveau_from_score(score: float) -> str:
    if score >= 8.0:
        return "VERY_LOW"
    if score >= 6.0:
        return "LOW"
    if score >= 4.0:
        return "MEDIUM"
    if score >= 2.0:
        return "HIGH"
    return "VERY_HIGH"


def generate_training_data(affluence_data: dict, n_per_cell: int = 25) -> tuple:
    creneaux = affluence_data["creneaux_horaires"]
    rng = np.random.default_rng(42)

    X, y = [], []
    for heure in range(24):
        base = _slot_score(heure, creneaux)
        for jour in range(7):
            is_weekend = 1 if jour >= 5 else 0
            for poids in [1, 2, 3]:
                for _ in range(n_per_cell):
                    facteur = {1: 1.0, 2: 0.8, 3: 0.6}[poids]
                    score = base * facteur

                    # Le week-end : les heures de pointe sont moins intenses
                    if is_weekend and base < 5:
                        score = score * 1.4

                    # Variabilité naturelle
                    score += rng.normal(0, 0.35)
                    score = float(np.clip(score, 0.0, 10.0))

                    X.append([heure, jour, is_weekend, poids])
                    y.append(score)

    return np.array(X), np.array(y)


def train(X, y):
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import cross_val_score

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=2,
        random_state=42,
    )
    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    model.fit(X, y)
    return model, -scores.mean()


def main():
    affluence_data = json.loads((DATA_DIR / "affluence.json").read_text(encoding="utf-8"))
    creneaux = affluence_data["creneaux_horaires"]

    print("Génération des données d'entraînement...")
    X, y = generate_training_data(affluence_data, n_per_cell=25)
    print(f"  {len(X)} échantillons générés")

    print("Entraînement du RandomForestRegressor...")
    model, mae = train(X, y)
    print(f"  MAE cross-validation : {mae:.3f}")

    MODEL_DIR.mkdir(exist_ok=True)
    meta = {
        "features":  ["heure", "jour_semaine", "is_weekend", "poids_station"],
        "creneaux":  creneaux,
        "mae_cv":    round(mae, 4),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)

    print(f"Modèle sauvegardé → {MODEL_PATH}")

    # Vérification rapide
    exemples = [
        ([2, 0, 0, 1], "Nuit (2h, lun, poids 1)"),
        ([8, 0, 0, 1], "Pointe matin (8h, lun, poids 1)"),
        ([8, 0, 0, 3], "Pointe matin (8h, lun, Châtelet)"),
        ([8, 5, 1, 1], "Week-end matin (8h, sam, poids 1)"),
        ([14, 0, 0, 1], "Milieu de journée (14h, lun, poids 1)"),
        ([17, 0, 0, 1], "Pointe soir (17h, lun, poids 1)"),
    ]
    print("\nVérification des prédictions :")
    for feat, label in exemples:
        pred = model.predict([feat])[0]
        print(f"  {label:<45} → score={pred:.2f}  niveau={_niveau_from_score(pred)}")


if __name__ == "__main__":
    main()
