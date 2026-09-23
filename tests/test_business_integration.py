import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.enricher import enrich


class BusinessIntegrationTests(unittest.TestCase):
    def test_enrich_produces_business_recommendation_and_alerts(self):
        journey = {
            "duration": 1800,
            "nb_transfers": 1,
            "sections": [
                {
                    "type": "public_transport",
                    "display_informations": {"label": "RER A"},
                    "stop_date_times": [
                        {
                            "stop_point": {"name": "Vincennes"},
                            "equipment_availability": {"elevator": "available"},
                        }
                    ],
                },
                {
                    "type": "transfer",
                    "duration": 180,
                    "transfer_type": "walk",
                },
                {
                    "type": "public_transport",
                    "display_informations": {"label": "Ligne 1"},
                    "stop_date_times": [
                        {
                            "stop_point": {"name": "La Défense"},
                            "equipment_availability": {"elevator": "available"},
                        }
                    ],
                },
            ],
            "disruptions": [],
        }

        result = enrich(journey, "20250624T083000")

        self.assertIn(result["recommandation"], {"Recommandé", "À considérer", "À éviter"})
        self.assertIsInstance(result["business_summary"]["alertes"], list)
        self.assertIsInstance(result["business_summary"]["points_forts"], list)
        self.assertGreaterEqual(result["score_confort"], 0)

    @patch("src.enricher._load_confort_model", return_value=None)
    def test_trajet_futur_sans_modele_reste_sur_les_regles(self, mock_load):
        journey = {
            "duration": 1200,
            "nb_transfers": 0,
            "sections": [
                {
                    "type": "public_transport",
                    "display_informations": {"label": "Ligne 1"},
                    "stop_date_times": [
                        {"stop_point": {"name": "La Défense"}, "equipment_availability": {}}
                    ],
                },
            ],
            "disruptions": [],
        }
        demain = (datetime.now() + timedelta(days=1)).strftime("%Y%m%dT160000")

        result = enrich(journey, demain)

        self.assertFalse(result["donnee_temps_reel"])
        self.assertEqual(result["score_confort_source"], "regles")

    def test_trajet_aujourd_hui_est_marque_temps_reel(self):
        journey = {
            "duration": 1200,
            "nb_transfers": 0,
            "sections": [
                {
                    "type": "public_transport",
                    "display_informations": {"label": "Ligne 1"},
                    "stop_date_times": [
                        {"stop_point": {"name": "La Défense"}, "equipment_availability": {}}
                    ],
                },
            ],
            "disruptions": [],
        }
        maintenant = datetime.now().strftime("%Y%m%dT%H%M%S")

        result = enrich(journey, maintenant)

        self.assertTrue(result["donnee_temps_reel"])
        self.assertEqual(result["score_confort_source"], "regles")


if __name__ == "__main__":
    unittest.main()
