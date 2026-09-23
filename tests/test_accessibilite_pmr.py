import sys
import unittest

sys.path.insert(0, "src")

from enricher import _score_accessibilite, _build_business_summary


def _sections(stations):
    """Construit des sections public_transport à partir de (nom, equipment_availability)."""
    return [{
        "type": "public_transport",
        "stop_date_times": [
            {"stop_point": {"name": nom}, "equipment_availability": eq}
            for nom, eq in stations
        ],
    }]


DISPO  = {"elevator": "available"}
PANNE  = {"elevator": "unavailable"}
VIDE   = {}
UNKNOWN = {"elevator": "unknown"}


class TestStatutAccessibilite(unittest.TestCase):
    """L'absence de donnée ne doit jamais être servie comme une garantie."""

    def test_toutes_stations_verifiees_disponibles(self):
        r = _score_accessibilite(_sections([("Nation", DISPO), ("Lyon", DISPO)]))
        self.assertEqual(r["statut"], "accessible")
        self.assertTrue(r["ok"])

    def test_une_panne_detectee(self):
        r = _score_accessibilite(_sections([("Nation", DISPO), ("Lyon", PANNE)]))
        self.assertEqual(r["statut"], "panne")
        self.assertFalse(r["ok"])
        self.assertEqual([p["station"] for p in r["pannes"]], ["Lyon"])

    def test_aucune_donnee_equipement_est_inconnu(self):
        """Cas réel : IDFM ne renvoie aucun equipment_availability."""
        r = _score_accessibilite(_sections([("Nation", VIDE), ("Lyon", VIDE)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"], "sans donnée, le trajet ne doit pas être déclaré accessible")

    def test_elevator_unknown_est_inconnu(self):
        r = _score_accessibilite(_sections([("Nation", UNKNOWN)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])

    def test_une_seule_station_inconnue_suffit_a_degrader(self):
        """Une chaîne d'accessibilité vaut par son maillon le plus faible."""
        r = _score_accessibilite(_sections([("Nation", DISPO), ("Lyon", VIDE)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])
        self.assertEqual(r["inconnues"], ["Lyon"])

    def test_panne_prioritaire_sur_inconnu(self):
        r = _score_accessibilite(_sections([("Nation", PANNE), ("Lyon", VIDE)]))
        self.assertEqual(r["statut"], "panne")

    def test_trajet_sans_section_transport_est_inconnu(self):
        r = _score_accessibilite([{"type": "street_network"}])
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])

    def test_inconnues_listees_pour_affichage(self):
        r = _score_accessibilite(_sections([("Nation", VIDE), ("Lyon", VIDE)]))
        self.assertEqual(r["inconnues"], ["Nation", "Lyon"])
        self.assertEqual(r["nb_checked"], 0)


class TestFiltrePMR(unittest.TestCase):
    """Le filtre accessible ne doit laisser passer que le vérifié."""

    def _passe(self, stations):
        from api import _passe_filtres
        acc = _score_accessibilite(_sections(stations))
        itineraire = {"dimensions": {
            "accessibilite":  acc,
            "affluence":      {"niveau": "LOW"},
            "climatisation":  {"status": "total"},
        }}
        return _passe_filtres(itineraire, accessible=True, peu_de_monde=False, climatise=False)

    def test_verifie_accessible_passe(self):
        self.assertTrue(self._passe([("Nation", DISPO)]))

    def test_panne_ne_passe_pas(self):
        self.assertFalse(self._passe([("Nation", PANNE)]))

    def test_inconnu_ne_passe_pas(self):
        """Le cœur de la correction : "on ne sait pas" n'est pas "c'est accessible"."""
        self.assertFalse(self._passe([("Nation", VIDE)]))


class TestAlerteMetier(unittest.TestCase):
    """Une accessibilité inconnue ne doit pas être annoncée comme une panne."""

    def _alertes(self, statut):
        dims = {
            "accessibilite":  {"statut": statut, "ok": statut == "accessible"},
            "affluence":      {"score": 8},
            "climatisation":  {"status": "total"},
            "equipements":    {"score": 8},
            "correspondances": {"score": 8},
        }
        return _build_business_summary(dims, 8.0)

    def test_panne_annoncee_comme_panne(self):
        r = self._alertes("panne")
        self.assertIn("Ascenseur en panne", r["alertes"])

    def test_inconnu_non_annonce_comme_panne(self):
        r = self._alertes("inconnu")
        self.assertNotIn("Ascenseur en panne", r["alertes"])
        self.assertIn("Accessibilité non renseignée", r["alertes"])

    def test_inconnu_n_est_pas_un_point_fort(self):
        r = self._alertes("inconnu")
        self.assertNotIn("Accessibilité stable", r["points_forts"])

    def test_accessible_est_un_point_fort(self):
        r = self._alertes("accessible")
        self.assertIn("Accessibilité stable", r["points_forts"])
        self.assertEqual(r["alertes"], [])


if __name__ == "__main__":
    unittest.main()
