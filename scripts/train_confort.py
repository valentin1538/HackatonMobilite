"""
Entraîne un RandomForestRegressor pour prédire le score_confort global
d'un trajet à partir de l'historique des trajets réellement observés
(voir src/historique.py — alimenté automatiquement par l'API à chaque
appel avec une date du jour).

Plus l'historique grandit, plus la prédiction devient précise pour les
trajets futurs (src/enricher.py bascule sur ce modèle dès qu'il existe
suffisamment de données).

Usage :
    python scripts/train_confort.py
"""

import sys
import pickle
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "confort_model.pkl"

sys.path.insert(0, str(ROOT / "src"))
from historique import lire_historique, CONFORT_FEATURES, MIN_SAMPLES_CONFORT_MODEL, HISTORIQUE_PATH


def build_xy(rows: list) -> tuple:
    X, y = [], []
    for row in rows:
        try:
            features = [float(row[f]) for f in CONFORT_FEATURES]
            label = float(row["score_confort"])
        except (KeyError, ValueError, TypeError):
            continue  # ligne incomplète ou corrompue, ignorée
        X.append(features)
        y.append(label)
    return X, y


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
    rows = lire_historique()
    print(f"{len(rows)} trajet(s) dans l'historique ({HISTORIQUE_PATH})")

    X, y = build_xy(rows)

    if len(X) < MIN_SAMPLES_CONFORT_MODEL:
        print(
            f"Pas assez de données pour entraîner : {len(X)} trajet(s) exploitable(s), "
            f"{MIN_SAMPLES_CONFORT_MODEL} requis au minimum."
        )
        print("Le modèle existant (s'il y en a un) n'est pas modifié.")
        return

    print("Entraînement du RandomForestRegressor...")
    model, mae = train(X, y)
    print(f"  MAE cross-validation : {mae:.3f}")

    MODEL_DIR.mkdir(exist_ok=True)
    meta = {
        "features":   CONFORT_FEATURES,
        "n_samples":  len(X),
        "mae_cv":     round(mae, 4),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "meta": meta}, f)

    print(f"Modèle sauvegardé → {MODEL_PATH}")


if __name__ == "__main__":
    main()
