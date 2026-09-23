import sys
import unittest

sys.path.insert(0, "src")

from enricher import _score_accessibilite_sensorielle

VISUEL_ET_SONORE = ["has_visual_announcement", "has_audible_announcement"]
VISUEL_SEUL      = ["has_visual_announcement"]
AUCUN            = []


def _sections(stations):
    return [{
        "type": "public_transport",
        "stop_date_times": [
            {"stop_point": {"name": nom, "equipments": eq}} for nom, eq in stations
        ],
    }]


class TestAccessibiliteSensorielle(unittest.TestCase):
    def test_tous_equipes(self):
        r = _score_accessibilite_sensorielle(_sections([
            ("Olympiades", VISUEL_ET_SONORE), ("Saint-Lazare", VISUEL_ET_SONORE)]))
        self.assertEqual(r["statut"], "complete")
        self.assertEqual(r["score"], 10)
        self.assertEqual(r["manquants"], [])

    def test_partiellement_equipes(self):
        r = _score_accessibilite_sensorielle(_sections([
            ("Olympiades", VISUEL_ET_SONORE), ("Saint-Lazare", VISUEL_SEUL)]))
        self.assertEqual(r["statut"], "partielle")
        self.assertEqual(r["manquants"], ["Saint-Lazare"])
        self.assertEqual(r["visuel"], 2)
        self.assertEqual(r["sonore"], 1)

    def test_aucun_equipement(self):
        r = _score_accessibilite_sensorielle(_sections([
            ("A", AUCUN), ("B", AUCUN)]))
        self.assertEqual(r["statut"], "aucune")
        self.assertEqual(r["score"], 3)

    def test_sans_section_transport(self):
        r = _score_accessibilite_sensorielle([{"type": "street_network"}])
        self.assertEqual(r["statut"], "inconnu")
        self.assertEqual(r["total"], 0)

    def test_arrets_traverses_ignores(self):
        """Meme regle que l'accessibilite fauteuil : montee et descente seules."""
        r = _score_accessibilite_sensorielle(_sections([
            ("Depart", VISUEL_ET_SONORE), ("Traverse", AUCUN), ("Arrivee", VISUEL_ET_SONORE)]))
        self.assertEqual(r["statut"], "complete")
        self.assertEqual(r["total"], 2)

    def test_n_entre_pas_dans_le_score_de_confort(self):
        """Dimension informative : verifie qu'elle reste hors formule."""
        import inspect
        from enricher import enrich
        src = inspect.getsource(enrich)
        formule = src[src.index("score_confort = round("):src.index("malus_meteo")]
        self.assertNotIn("sens[", formule)


if __name__ == "__main__":
    unittest.main()
