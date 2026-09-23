import sys
import unittest

sys.path.insert(0, "src")

from enricher import _score_meteo


CANICULE = {"temperature": 37, "precipitation": 0, "weathercode": 0}
PLUIE    = {"temperature": 18, "precipitation": 2.0, "weathercode": 61}
CHALEUR  = {"temperature": 30, "precipitation": 0, "weathercode": 0}

AERIENNES = {"cambronne": {"position": "elevated", "ligne": "6"}}


def _malus(meteo, stations, clim_status):
    """Malus accumulé sur la dimension météo (0 = aucune pénalité)."""
    return 10.0 - _score_meteo(meteo, stations, AERIENNES, clim_status)["score"]


class TestCaniculeEtClimatisation(unittest.TestCase):
    """La canicule doit pénaliser selon la climatisation du trajet, pas uniformément."""

    def test_trajet_climatise_non_penalise(self):
        self.assertEqual(_malus(CANICULE, ["Nation"], "total"), 0.0)

    def test_trajet_non_climatise_penalise_au_maximum(self):
        self.assertEqual(_malus(CANICULE, ["Nation"], "aucune"), 2.0)

    def test_trajet_partiellement_climatise_penalise_a_moitie(self):
        self.assertEqual(_malus(CANICULE, ["Nation"], "partiel"), 1.0)

    def test_clim_inconnue_penalise_a_moitie(self):
        self.assertEqual(_malus(CANICULE, ["Nation"], "inconnu"), 1.0)

    def test_la_canicule_departage_les_itineraires(self):
        """Le point de la correction : deux trajets ne doivent plus être à égalité."""
        climatise = _malus(CANICULE, ["Nation"], "total")
        sans_clim = _malus(CANICULE, ["Nation"], "aucune")
        self.assertLess(climatise, sans_clim)

    def test_alerte_mentionne_la_climatisation(self):
        alertes = _score_meteo(CANICULE, ["Nation"], AERIENNES, "aucune")["alertes"]
        self.assertIn("Canicule : trajet non climatisé", alertes)

    def test_pas_de_canicule_en_dessous_du_seuil(self):
        self.assertEqual(_malus(CHALEUR, ["Nation"], "aucune"), 0.0)

    def test_chaleur_moderee_signalee_seulement_si_pas_climatise(self):
        avec = _score_meteo(CHALEUR, ["Nation"], AERIENNES, "total")["alertes"]
        sans = _score_meteo(CHALEUR, ["Nation"], AERIENNES, "aucune")["alertes"]
        self.assertEqual(avec, [])
        self.assertIn("Chaleur : vérifiez la climatisation", sans)


class TestPluieAerien(unittest.TestCase):
    """Non-régression : la pluie reste conditionnée aux stations aériennes."""

    def test_pluie_sur_trajet_souterrain_sans_malus(self):
        self.assertEqual(_malus(PLUIE, ["Nation"], "total"), 0.0)

    def test_pluie_sur_trajet_aerien_penalisee(self):
        self.assertEqual(_malus(PLUIE, ["Cambronne"], "total"), 2.0)

    def test_pluie_et_canicule_se_cumulent(self):
        orage = {"temperature": 37, "precipitation": 2.0, "weathercode": 61}
        self.assertEqual(_malus(orage, ["Cambronne"], "aucune"), 4.0)


if __name__ == "__main__":
    unittest.main()
