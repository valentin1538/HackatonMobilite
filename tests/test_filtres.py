import sys
import unittest

sys.path.insert(0, "src")

from api import _flags_filtres, _passe_filtres


def _itineraire(statut_acc="accessible", niveau="LOW", clim="total"):
    return {"dimensions": {
        "accessibilite": {"statut": statut_acc},
        "affluence":     {"niveau": niveau},
        "climatisation": {"status": clim},
    }}


class TestFiltreClimatise(unittest.TestCase):
    """Comme pour le PMR : une climatisation non renseignée n'est pas une garantie."""

    def test_ligne_climatisee_passe(self):
        self.assertTrue(_flags_filtres(_itineraire(clim="total"))["climatise"])

    def test_ligne_partiellement_climatisee_passe(self):
        self.assertTrue(_flags_filtres(_itineraire(clim="partiel"))["climatise"])

    def test_ligne_non_climatisee_ne_passe_pas(self):
        self.assertFalse(_flags_filtres(_itineraire(clim="aucune"))["climatise"])

    def test_clim_inconnue_ne_passe_pas(self):
        """Le défaut de climatisation.json est "inconnu" : il ne doit pas passer."""
        self.assertFalse(_flags_filtres(_itineraire(clim="inconnu"))["climatise"])


class TestFiltrePeuDeMonde(unittest.TestCase):
    """Seuil unique : "peu de monde" veut dire LOW ou VERY_LOW, nulle part ailleurs."""

    def test_niveaux_calmes_passent(self):
        for niveau in ("LOW", "VERY_LOW"):
            with self.subTest(niveau=niveau):
                self.assertTrue(_flags_filtres(_itineraire(niveau=niveau))["peu_de_monde"])

    def test_niveaux_charges_ne_passent_pas(self):
        for niveau in ("MEDIUM", "HIGH", "VERY_HIGH"):
            with self.subTest(niveau=niveau):
                self.assertFalse(_flags_filtres(_itineraire(niveau=niveau))["peu_de_monde"])

    def test_medium_exclu(self):
        """Le front gardait MEDIUM, l'API l'excluait : divergence corrigée."""
        self.assertFalse(_flags_filtres(_itineraire(niveau="MEDIUM"))["peu_de_monde"])


class TestFiltreAccessible(unittest.TestCase):
    def test_seul_le_statut_verifie_passe(self):
        self.assertTrue(_flags_filtres(_itineraire(statut_acc="accessible"))["accessible"])
        self.assertFalse(_flags_filtres(_itineraire(statut_acc="panne"))["accessible"])
        self.assertFalse(_flags_filtres(_itineraire(statut_acc="inconnu"))["accessible"])


class TestCoherenceDrapeauxEtFiltrage(unittest.TestCase):
    """_passe_filtres et les drapeaux exposés au front doivent être d'accord.

    C'est la garantie que le filtrage serveur et le filtrage client ne peuvent
    plus diverger : ils dérivent tous deux de _flags_filtres.
    """

    def test_tous_les_cas_concordent(self):
        statuts = ("accessible", "panne", "inconnu")
        niveaux = ("VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH")
        clims   = ("total", "partiel", "aucune", "inconnu")

        for s in statuts:
            for n in niveaux:
                for c in clims:
                    it = _itineraire(s, n, c)
                    flags = _flags_filtres(it)
                    for actif in ("accessible", "peu_de_monde", "climatise"):
                        kwargs = {"accessible": False, "peu_de_monde": False, "climatise": False}
                        kwargs[actif] = True
                        with self.subTest(statut=s, niveau=n, clim=c, filtre=actif):
                            self.assertEqual(_passe_filtres(it, **kwargs), flags[actif])

    def test_filtres_cumules(self):
        parfait = _itineraire("accessible", "LOW", "total")
        self.assertTrue(_passe_filtres(parfait, True, True, True))
        boiteux = _itineraire("accessible", "LOW", "inconnu")
        self.assertFalse(_passe_filtres(boiteux, True, True, True))

    def test_aucun_filtre_actif_laisse_tout_passer(self):
        pire = _itineraire("inconnu", "VERY_HIGH", "aucune")
        self.assertTrue(_passe_filtres(pire, False, False, False))


if __name__ == "__main__":
    unittest.main()
