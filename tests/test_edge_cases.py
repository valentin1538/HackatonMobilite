import sys
import unittest

sys.path.insert(0, "src")

from enricher import enrich, _score_affluence, _score_climatisation, _score_correspondances
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
_affluence = json.loads((DATA_DIR / "affluence.json").read_text(encoding="utf-8"))
_clim = json.loads((DATA_DIR / "climatisation.json").read_text(encoding="utf-8"))


def _journey(lignes=None, stations=None, transfers=None, elevators=None, disruptions=None):
    """Construit un itinéraire minimal pour les tests."""
    lignes = lignes or ["A"]
    stations = stations or ["Gare X"]
    transfers = transfers or []
    elevators = elevators or ["available"] * len(stations)

    sections = []
    for i, ligne in enumerate(lignes):
        stop = stations[i] if i < len(stations) else stations[0]
        elev = elevators[i] if i < len(elevators) else "available"
        sections.append({
            "type": "public_transport",
            "display_informations": {"label": ligne},
            "stop_date_times": [{
                "stop_point": {"name": stop},
                "equipment_availability": {"elevator": elev},
            }],
        })
    for dur in transfers:
        sections.append({"type": "transfer", "duration": dur, "transfer_type": "walk"})

    return {
        "duration": 1200,
        "nb_transfers": len(transfers),
        "sections": sections,
        "disruptions": disruptions or [],
    }


class TestNuit(unittest.TestCase):
    def test_affluence_nuit(self):
        score = _score_affluence(2, ["Gare X"], _affluence)
        self.assertEqual(score["niveau"], "VERY_LOW")
        self.assertGreaterEqual(score["score"], 8.0)

    def test_enrich_nuit(self):
        result = enrich(_journey(), "20260626T020000")
        self.assertEqual(result["dimensions"]["affluence"]["niveau"], "VERY_LOW")
        self.assertGreaterEqual(result["score_confort"], 7.0)


class TestHeureDePointe(unittest.TestCase):
    def test_affluence_pointe_matin(self):
        score = _score_affluence(8, ["Gare X"], _affluence)
        self.assertEqual(score["niveau"], "VERY_HIGH")
        self.assertLessEqual(score["score"], 2.5)

    def test_affluence_pointe_soir(self):
        score = _score_affluence(17, ["Gare X"], _affluence)
        self.assertEqual(score["niveau"], "VERY_HIGH")
        self.assertLessEqual(score["score"], 2.5)


class TestGrandeGare(unittest.TestCase):
    def test_grande_gare_reduit_score_affluence(self):
        score_std   = _score_affluence(8, ["Gare X"],      _affluence)
        score_grande = _score_affluence(8, ["Gare du Nord"], _affluence)
        self.assertLessEqual(score_std["score"], 2.5)
        self.assertLessEqual(score_grande["score"], score_std["score"])

    def test_chatelet_pointe_score_tres_bas(self):
        score = _score_affluence(8, ["Châtelet - Les Halles"], _affluence)
        self.assertEqual(score["poids_station"], 3)
        self.assertLessEqual(score["score"], 1.5)


class TestClimatisation(unittest.TestCase):
    def test_metro_1_clim_totale(self):
        result = _score_climatisation(["1"], _clim)
        self.assertEqual(result["status"], "total")
        self.assertEqual(result["score"], 10)

    def test_metro_5_sans_clim(self):
        result = _score_climatisation(["5"], _clim)
        self.assertEqual(result["status"], "aucune")
        self.assertEqual(result["score"], 2)

    def test_rer_a_partiel(self):
        result = _score_climatisation(["A"], _clim)
        self.assertEqual(result["status"], "partiel")
        self.assertEqual(result["score"], 6)

    def test_trajet_mixte_prend_le_pire(self):
        result = _score_climatisation(["1", "5"], _clim)
        self.assertEqual(result["status"], "aucune")

    def test_ligne_inconnue_renvoie_default(self):
        result = _score_climatisation(["Z"], _clim)
        self.assertEqual(result["status"], "inconnu")


class TestCorrespondances(unittest.TestCase):
    def test_sans_correspondance(self):
        result = enrich(_journey(transfers=[]), "20260626T083000")
        self.assertEqual(result["dimensions"]["correspondances"]["nb"], 0)
        self.assertEqual(result["dimensions"]["correspondances"]["score"], 10)

    def test_correspondance_courte(self):
        result = _score_correspondances([{"type": "transfer", "duration": 90}])
        self.assertEqual(result["score"], 9)

    def test_correspondance_longue(self):
        result = _score_correspondances([{"type": "transfer", "duration": 700}])
        self.assertEqual(result["score"], 3)

    def test_rer_longue_distance_avec_correspondance(self):
        # 480s de correspondance → tranche 300-600s → score 5
        j = _journey(lignes=["A", "B"], stations=["Gare X", "Gare Y"], transfers=[480])
        result = enrich(j, "20260626T143000")
        self.assertEqual(result["dimensions"]["correspondances"]["score"], 5)


class TestAccessibilite(unittest.TestCase):
    def test_ascenseur_disponible(self):
        result = enrich(_journey(elevators=["available"]), "20260626T083000")
        self.assertTrue(result["dimensions"]["accessibilite"]["ok"])
        self.assertEqual(result["dimensions"]["accessibilite"]["score"], 10)

    def test_ascenseur_en_panne(self):
        result = enrich(_journey(elevators=["unavailable"]), "20260626T083000")
        self.assertFalse(result["dimensions"]["accessibilite"]["ok"])
        self.assertLess(result["dimensions"]["accessibilite"]["score"], 10)
        self.assertEqual(len(result["dimensions"]["accessibilite"]["pannes"]), 1)

    def test_plusieurs_pannes(self):
        j = _journey(lignes=["1", "4"], stations=["A", "B"], elevators=["unavailable", "unavailable"])
        result = enrich(j, "20260626T083000")
        self.assertEqual(len(result["dimensions"]["accessibilite"]["pannes"]), 2)
        self.assertLessEqual(result["dimensions"]["accessibilite"]["score"], 4)


class TestBusinessSummary(unittest.TestCase):
    def test_score_eleve_est_recommande(self):
        j = _journey(lignes=["1"], stations=["Gare X"], elevators=["available"])
        result = enrich(j, "20260626T230000")
        self.assertIn(result["recommandation"], {"Recommandé", "À considérer", "À éviter"})

    def test_alertes_sont_une_liste(self):
        result = enrich(_journey(), "20260626T083000")
        self.assertIsInstance(result["business_summary"]["alertes"], list)
        self.assertIsInstance(result["business_summary"]["points_forts"], list)

    def test_panne_genere_alerte(self):
        result = enrich(_journey(elevators=["unavailable"]), "20260626T083000")
        self.assertIn("Ascenseur en panne", result["business_summary"]["alertes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
