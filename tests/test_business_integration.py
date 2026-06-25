import unittest

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


if __name__ == "__main__":
    unittest.main()
