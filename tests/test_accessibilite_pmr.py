import sys
import unittest

sys.path.insert(0, "src")

from enricher import _score_accessibilite, _build_business_summary


def _sections(stations):
    """Sections public_transport à partir de (nom, equipments, equipment_availability).

    Reproduit la structure réelle d'IDFM : les équipements présents sont listés
    dans stop_point["equipments"] ; equipment_availability porte l'état temps
    réel des ascenseurs, non renvoyé par le marketplace à ce jour.
    """
    return [{
        "type": "public_transport",
        "stop_date_times": [
            {
                "stop_point": {"name": nom, "equipments": equipements},
                "equipment_availability": dispo,
            }
            for nom, equipements, dispo in stations
        ],
    }]


# Arrêt documenté accessible en fauteuil
ACCESSIBLE = ["has_wheelchair_boarding", "has_audible_announcement"]
# Arrêt sans mention d'embarquement fauteuil : non documenté, pas "non accessible"
NON_DOCUMENTE = ["has_visual_announcement", "has_audible_announcement"]
SANS_EQUIPEMENT = []

PANNE_ASC = {"elevator": "unavailable"}
PAS_DE_TEMPS_REEL = {}


def _stop(nom, equipements=ACCESSIBLE, dispo=None):
    return (nom, equipements, dispo if dispo is not None else PAS_DE_TEMPS_REEL)


class TestStatutAccessibilite(unittest.TestCase):
    """L'absence de donnée ne doit jamais être servie comme une garantie."""

    def test_toutes_stations_verifiees_disponibles(self):
        r = _score_accessibilite(_sections([_stop("Nation"), _stop("Lyon")]))
        self.assertEqual(r["statut"], "accessible")
        self.assertTrue(r["ok"])

    def test_une_panne_detectee(self):
        r = _score_accessibilite(_sections([_stop("Nation"), _stop("Lyon", dispo=PANNE_ASC)]))
        self.assertEqual(r["statut"], "panne")
        self.assertFalse(r["ok"])
        self.assertEqual([p["station"] for p in r["pannes"]], ["Lyon"])

    def test_aucune_donnee_equipement_est_inconnu(self):
        """Arrêt sans aucun équipement recensé."""
        r = _score_accessibilite(_sections([_stop("Nation", SANS_EQUIPEMENT), _stop("Lyon", SANS_EQUIPEMENT)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"], "sans donnée, le trajet ne doit pas être déclaré accessible")

    def test_equipement_non_documente_est_inconnu(self):
        r = _score_accessibilite(_sections([_stop("Nation", NON_DOCUMENTE)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])

    def test_une_seule_station_inconnue_suffit_a_degrader(self):
        """Une chaîne d'accessibilité vaut par son maillon le plus faible."""
        r = _score_accessibilite(_sections([_stop("Nation"), _stop("Lyon", NON_DOCUMENTE)]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])
        self.assertEqual(r["inconnues"], ["Lyon"])

    def test_panne_prioritaire_sur_inconnu(self):
        r = _score_accessibilite(_sections([_stop("Nation", dispo=PANNE_ASC), _stop("Lyon", SANS_EQUIPEMENT)]))
        self.assertEqual(r["statut"], "panne")

    def test_trajet_sans_section_transport_est_inconnu(self):
        r = _score_accessibilite([{"type": "street_network"}])
        self.assertEqual(r["statut"], "inconnu")
        self.assertFalse(r["ok"])

    def test_inconnues_listees_pour_affichage(self):
        r = _score_accessibilite(_sections([_stop("Nation", SANS_EQUIPEMENT), _stop("Lyon", SANS_EQUIPEMENT)]))
        self.assertEqual(r["inconnues"], ["Nation", "Lyon"])
        self.assertEqual(r["nb_checked"], 0)


class TestArretsUtilises(unittest.TestCase):
    """Seuls les arrêts de montée et descente comptent, pas ceux traversés."""

    def test_arret_intermediaire_non_documente_ignore(self):
        """Cas réel ligne 14 : Gare de Lyon n'est pas documentée mais on ne fait
        que la traverser entre Olympiades et Saint-Lazare."""
        r = _score_accessibilite(_sections([
            _stop("Olympiades"),
            _stop("Gare de Lyon", NON_DOCUMENTE),   # traversee
            _stop("Saint-Lazare"),
        ]))
        self.assertEqual(r["statut"], "accessible")
        self.assertEqual(r["nb_checked"], 2)

    def test_arret_de_descente_non_documente_degrade(self):
        r = _score_accessibilite(_sections([
            _stop("Olympiades"),
            _stop("Chatelet"),
            _stop("Saint-Lazare", NON_DOCUMENTE),   # terminus du trajet
        ]))
        self.assertEqual(r["statut"], "inconnu")
        self.assertEqual(r["inconnues"], ["Saint-Lazare"])

    def test_correspondance_compte_comme_montee_descente(self):
        """Deux sections : les 4 extremites comptent, les traversees non."""
        sections = _sections([_stop("A"), _stop("X", NON_DOCUMENTE), _stop("B")]) +                    _sections([_stop("B"), _stop("Y", NON_DOCUMENTE), _stop("C")])
        r = _score_accessibilite(sections)
        self.assertEqual(r["statut"], "accessible")
        self.assertEqual(r["nb_checked"], 4)

    def test_section_a_un_seul_arret(self):
        r = _score_accessibilite(_sections([_stop("Nation")]))
        self.assertEqual(r["statut"], "accessible")


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
        self.assertTrue(self._passe([_stop("Nation")]))

    def test_panne_ne_passe_pas(self):
        self.assertFalse(self._passe([_stop("Nation", dispo=PANNE_ASC)]))

    def test_inconnu_ne_passe_pas(self):
        """Le cœur de la correction : "non documenté" n'est pas "c'est accessible"."""
        self.assertFalse(self._passe([_stop("Nation", SANS_EQUIPEMENT)]))


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
        self.assertIn("Accessibilité non documentée", r["alertes"])

    def test_inconnu_n_est_pas_un_point_fort(self):
        r = self._alertes("inconnu")
        self.assertNotIn("Accessibilité stable", r["points_forts"])

    def test_accessible_est_un_point_fort(self):
        r = self._alertes("accessible")
        self.assertIn("Accessibilité stable", r["points_forts"])
        self.assertEqual(r["alertes"], [])


if __name__ == "__main__":
    unittest.main()
