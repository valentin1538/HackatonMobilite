import sys
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import train_confort


def _fake_row(heure=8, jour_semaine=0, score_confort=7.0):
    return {
        "heure":               heure,
        "jour_semaine":        jour_semaine,
        "is_weekend":          int(jour_semaine >= 5),
        "affluence_score":     6.0,
        "climatisation_score": 10,
        "equipements_score":   5,
        "nb_correspondances":  1,
        "meteo_temperature":   15.0,
        "meteo_precipitation": 0.0,
        "score_confort":       score_confort,
    }


class TestTrainConfort(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._original_model_dir = train_confort.MODEL_DIR
        self._original_model_path = train_confort.MODEL_PATH
        train_confort.MODEL_DIR = Path(self._tmp.name)
        train_confort.MODEL_PATH = train_confort.MODEL_DIR / "confort_model.pkl"

    def tearDown(self):
        train_confort.MODEL_DIR = self._original_model_dir
        train_confort.MODEL_PATH = self._original_model_path
        self._tmp.cleanup()

    @patch("train_confort.lire_historique")
    def test_refuse_d_entrainer_sous_le_seuil(self, mock_lire):
        mock_lire.return_value = [_fake_row() for _ in range(5)]
        train_confort.main()
        self.assertFalse(train_confort.MODEL_PATH.exists())

    @patch("train_confort.lire_historique")
    def test_entraine_au_dessus_du_seuil(self, mock_lire):
        rows = [_fake_row(heure=h % 24, score_confort=5.0 + (h % 5)) for h in range(60)]
        mock_lire.return_value = rows

        train_confort.main()

        self.assertTrue(train_confort.MODEL_PATH.exists())
        with open(train_confort.MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        self.assertEqual(bundle["meta"]["n_samples"], 60)
        self.assertIn("mae_cv", bundle["meta"])
        self.assertEqual(bundle["meta"]["features"], train_confort.CONFORT_FEATURES)

    @patch("train_confort.lire_historique")
    def test_ignore_les_lignes_incompletes(self, mock_lire):
        rows = [_fake_row(heure=h % 24, score_confort=5.0 + (h % 5)) for h in range(60)]
        rows.append({"heure": 8})  # ligne corrompue, doit être ignorée sans planter
        mock_lire.return_value = rows

        train_confort.main()

        with open(train_confort.MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        self.assertEqual(bundle["meta"]["n_samples"], 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
