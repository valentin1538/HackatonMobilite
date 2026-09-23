import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, "src")

from enricher import _fetch_meteo, _is_future


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _dans(heures: float) -> str:
    """Construit un departure_dt à +`heures` de l'instant présent (peut être négatif)."""
    return (datetime.now() + timedelta(hours=heures)).strftime("%Y%m%dT%H%M%S")


class TestIsFuture(unittest.TestCase):
    def test_maintenant_n_est_pas_futur(self):
        self.assertFalse(_is_future(_dans(0)))

    def test_dans_10_minutes_n_est_pas_futur(self):
        self.assertFalse(_is_future(_dans(10 / 60)))

    def test_dans_3_heures_est_futur(self):
        # Motive ce fix : "aujourd'hui dans 3h" doit être traité comme un trajet
        # futur, pas comme une observation temps réel — même jour ou non.
        self.assertTrue(_is_future(_dans(3)))

    def test_demain_est_futur(self):
        self.assertTrue(_is_future(_dans(24)))

    def test_passe_n_est_pas_futur(self):
        self.assertFalse(_is_future(_dans(-2)))


class TestFetchMeteo(unittest.TestCase):
    @patch("enricher._requests.get")
    def test_proche_de_maintenant_utilise_current(self, mock_get):
        mock_get.return_value = _FakeResponse({
            "current": {"temperature_2m": 12.0, "precipitation": 0.0, "weathercode": 1}
        })
        result = _fetch_meteo(_dans(0.1))  # 6 minutes

        self.assertEqual(result["temperature"], 12.0)
        params = mock_get.call_args.kwargs["params"]
        self.assertIn("current", params)
        self.assertNotIn("hourly", params)

    @patch("enricher._requests.get")
    def test_quelques_heures_plus_tard_utilise_les_previsions(self, mock_get):
        cible = datetime.now() + timedelta(hours=3)
        cible_str = f"{cible.date().isoformat()}T{cible.hour:02d}:00"
        mock_get.return_value = _FakeResponse({
            "hourly": {
                "time":           ["2000-01-01T00:00", cible_str],
                "temperature_2m": [0.0, 19.0],
                "precipitation":  [0.0, 0.4],
                "weathercode":    [0, 3],
            }
        })
        result = _fetch_meteo(cible.strftime("%Y%m%dT%H%M%S"))

        self.assertEqual(result["temperature"], 19.0)
        params = mock_get.call_args.kwargs["params"]
        self.assertIn("hourly", params)
        self.assertNotIn("current", params)

    @patch("enricher._requests.get")
    def test_date_future_utilise_les_previsions(self, mock_get):
        cible = datetime.now() + timedelta(days=2)
        cible_str = f"{cible.date().isoformat()}T16:00"
        mock_get.return_value = _FakeResponse({
            "hourly": {
                "time":           ["2000-01-01T00:00", cible_str],
                "temperature_2m": [0.0, 22.5],
                "precipitation":  [0.0, 1.2],
                "weathercode":    [0, 61],
            }
        })
        dt = cible.strftime("%Y%m%dT160000")
        result = _fetch_meteo(dt)

        self.assertEqual(result["temperature"], 22.5)
        self.assertEqual(result["precipitation"], 1.2)
        params = mock_get.call_args.kwargs["params"]
        self.assertIn("hourly", params)
        self.assertNotIn("current", params)

    @patch("enricher._requests.get")
    def test_date_hors_plage_ne_fait_aucun_appel(self, mock_get):
        cible = datetime.now() + timedelta(days=30)
        dt = cible.strftime("%Y%m%dT160000")
        result = _fetch_meteo(dt)

        mock_get.assert_not_called()
        self.assertIsNone(result["temperature"])

    @patch("enricher._requests.get", side_effect=Exception("network error"))
    def test_echec_reseau_renvoie_valeurs_par_defaut(self, mock_get):
        result = _fetch_meteo(_dans(0.1))
        self.assertIsNone(result["temperature"])
        self.assertEqual(result["precipitation"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
