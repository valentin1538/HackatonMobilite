import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, "src")

import historique


def _enrichi(score_confort=7.5, temperature=18.0):
    return {
        "lignes": ["1"],
        "score_confort": score_confort,
        "dimensions": {
            "affluence":       {"score": 6.0},
            "climatisation":   {"score": 10},
            "accessibilite":   {"score": 10},
            "correspondances": {"score": 9, "nb": 1},
            "equipements":     {"score": 5},
            "meteo":           {"temperature": temperature, "precipitation": 0},
        },
    }


class TestHistorique(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._original_path = historique.HISTORIQUE_PATH
        historique.HISTORIQUE_PATH = Path(self._tmp.name) / "historique_trajets.csv"

    def tearDown(self):
        historique.HISTORIQUE_PATH = self._original_path
        self._tmp.cleanup()

    def test_log_trajet_cree_le_fichier_avec_en_tete(self):
        historique.log_trajet("Gare X", "Gare Y", "20260626T083000", _enrichi())
        self.assertTrue(historique.HISTORIQUE_PATH.exists())
        lignes = historique.HISTORIQUE_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lignes[0].split(",")[0], "logged_at")

    def test_log_trajet_ajoute_sans_dupliquer_en_tete(self):
        historique.log_trajet("Gare X", "Gare Y", "20260626T083000", _enrichi())
        historique.log_trajet("Gare X", "Gare Y", "20260626T173000", _enrichi(score_confort=5.0))
        lignes = historique.HISTORIQUE_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 3)  # 1 en-tête + 2 lignes

    def test_lire_historique_retourne_les_lignes_ecrites(self):
        historique.log_trajet("Gare X", "Gare Y", "20260626T083000", _enrichi(score_confort=7.5))
        rows = historique.lire_historique()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["station_dep"], "Gare X")
        self.assertEqual(float(rows[0]["score_confort"]), 7.5)
        self.assertEqual(int(rows[0]["heure"]), 8)

    def test_lire_historique_vide_si_fichier_absent(self):
        self.assertEqual(historique.lire_historique(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
