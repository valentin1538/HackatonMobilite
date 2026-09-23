import sys
import unittest

sys.path.insert(0, "src")

from enricher import _heure, _est_uniquement_a_pied, filtrer_journeys


def _journey_pt(depart="20260924T083103", arrivee="20260924T084442", tags=None):
    return {
        "departure_date_time": depart,
        "arrival_date_time":   arrivee,
        "duration": 780,
        "tags": tags or ["walking", "reliable"],
        "sections": [
            {"type": "crow_fly", "duration": 0},
            {"type": "public_transport", "duration": 780,
             "display_informations": {"label": "14"}, "stop_date_times": []},
        ],
    }


def _journey_marche(minutes=113):
    return {
        "departure_date_time": "20260924T083000",
        "arrival_date_time":   "20260924T102307",
        "duration": minutes * 60,
        "tags": ["non_pt", "non_pt_walking", "walking"],
        "sections": [{"type": "street_network", "duration": minutes * 60}],
    }


class TestHeure(unittest.TestCase):
    def test_format_navitia(self):
        self.assertEqual(_heure("20260924T083103"), "08:31")

    def test_minuit(self):
        self.assertEqual(_heure("20260924T000500"), "00:05")

    def test_valeur_invalide(self):
        self.assertIsNone(_heure("pas une date"))

    def test_valeur_absente(self):
        self.assertIsNone(_heure(None))


class TestDetectionMarche(unittest.TestCase):
    def test_tag_non_pt(self):
        self.assertTrue(_est_uniquement_a_pied(_journey_marche()))

    def test_trajet_en_transport(self):
        self.assertFalse(_est_uniquement_a_pied(_journey_pt()))

    def test_sans_tag_mais_sans_transport(self):
        """Repli si Navitia ne pose pas le tag : aucune section public_transport."""
        j = {"tags": [], "sections": [{"type": "street_network", "duration": 600}]}
        self.assertTrue(_est_uniquement_a_pied(j))


class TestFiltrageMarche(unittest.TestCase):
    def test_marche_ecartee_si_alternative(self):
        journeys = [_journey_pt(), _journey_pt("20260924T083238"), _journey_marche()]
        r = filtrer_journeys(journeys)
        self.assertEqual(len(r), 2)
        self.assertTrue(all(not _est_uniquement_a_pied(j) for j in r))

    def test_marche_conservee_si_seule_option(self):
        """Sur une courte distance, marcher est une vraie reponse."""
        journeys = [_journey_marche(minutes=8)]
        self.assertEqual(filtrer_journeys(journeys), journeys)

    def test_liste_vide(self):
        self.assertEqual(filtrer_journeys([]), [])

    def test_ordre_preserve(self):
        a, b = _journey_pt("20260924T080000"), _journey_pt("20260924T081000")
        r = filtrer_journeys([a, _journey_marche(), b])
        self.assertEqual(r, [a, b])


class TestHorairesDansEnrichissement(unittest.TestCase):
    def test_horaires_exposes(self):
        from enricher import enrich
        r = enrich(_journey_pt(), "20260924T083000")
        self.assertEqual(r["heure_depart"], "08:31")
        self.assertEqual(r["heure_arrivee"], "08:44")

    def test_deux_trains_distincts_par_l_horaire(self):
        """Le cas signale : deux fois la ligne 14, meme duree, horaires differents."""
        from enricher import enrich
        a = enrich(_journey_pt("20260924T083103", "20260924T084442"), "20260924T083000")
        b = enrich(_journey_pt("20260924T083238", "20260924T084617"), "20260924T083000")
        self.assertEqual(a["duree_min"], b["duree_min"])
        self.assertNotEqual(a["heure_depart"], b["heure_depart"])


if __name__ == "__main__":
    unittest.main()
