import sys
import unittest

sys.path.insert(0, "src")

from enricher import classer, _tri_confort


def _it(score, duree=20, depart="08:30", nom=None):
    return {"score_confort": score, "duree_min": duree, "heure_depart": depart,
            "lignes": [nom or str(score)]}


class TestMeilleurChoixUnique(unittest.TestCase):
    """Un comparateur qui recommande toutes les options ne recommande rien."""

    def test_un_seul_meilleur_choix(self):
        r = classer([_it(7.1), _it(7.5), _it(6.0)])
        self.assertEqual(sum(1 for it in r if it["meilleur_choix"]), 1)

    def test_le_meilleur_est_le_mieux_note(self):
        r = classer([_it(7.1), _it(7.5), _it(6.0)])
        self.assertEqual(r[0]["score_confort"], 7.5)
        self.assertTrue(r[0]["meilleur_choix"])

    def test_cas_signale_deux_recommandes(self):
        """Bastille -> Trocadero : 1+6 a 7.1 et 1 a 7.6, tous deux >= 7."""
        r = classer([_it(7.1, duree=23, nom="1+6"), _it(7.6, duree=37, nom="1")])
        best = [it for it in r if it["meilleur_choix"]]
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0]["lignes"], ["1"])

    def test_egalite_parfaite_departagee(self):
        """Deux trains identiques : un seul badge, le plus tot."""
        r = classer([_it(7.6, 7, "14:05"), _it(7.6, 7, "14:02")])
        self.assertEqual(sum(1 for it in r if it["meilleur_choix"]), 1)
        self.assertEqual(r[0]["heure_depart"], "14:02")

    def test_un_seul_itineraire(self):
        r = classer([_it(4.0)])
        self.assertTrue(r[0]["meilleur_choix"])

    def test_liste_vide(self):
        self.assertEqual(classer([]), [])

    def test_rang_attribue(self):
        r = classer([_it(5.0), _it(8.0), _it(6.5)])
        self.assertEqual([it["rang"] for it in r], [1, 2, 3])


class TestTriParConfort(unittest.TestCase):
    def test_ordre_decroissant(self):
        r = classer([_it(5.2), _it(7.8), _it(6.1)])
        self.assertEqual([it["score_confort"] for it in r], [7.8, 6.1, 5.2])

    def test_egalite_departagee_par_duree(self):
        r = classer([_it(7.0, duree=40), _it(7.0, duree=15)])
        self.assertEqual([it["duree_min"] for it in r], [15, 40])

    def test_egalite_score_et_duree_departagee_par_heure(self):
        r = classer([_it(7.0, 20, "09:15"), _it(7.0, 20, "08:45")])
        self.assertEqual([it["heure_depart"] for it in r], ["08:45", "09:15"])

    def test_horaire_absent_relegue_en_dernier(self):
        sans = {"score_confort": 7.0, "duree_min": 20, "lignes": ["X"]}
        r = classer([sans, _it(7.0, 20, "08:45")])
        self.assertEqual(r[0]["heure_depart"], "08:45")

    def test_cle_de_tri_est_comparable(self):
        self.assertLess(_tri_confort(_it(8.0)), _tri_confort(_it(6.0)))


if __name__ == "__main__":
    unittest.main()
