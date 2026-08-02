"""Responsibility Engine — concept métier détecté PAR LES VALEURS, puis décideur.

Le routage ne dépend plus du nom de la colonne : un axe opaque dont les valeurs
sont des régions est reconnu comme « zone géographique » → Directeur réseau.
"""
from __future__ import annotations

from app.services import responsibility as resp


def test_concept_from_values_geography_even_when_name_is_opaque():
    """Colonne opaque « a3 » mais valeurs = régions → zone géographique → réseau."""
    r = resp.resolve("a3", segment="Provence-Alpes-Côte d'Azur",
                     samples=["Île-de-France", "Auvergne-Rhône-Alpes", "Hauts-de-France"])
    assert r is not None
    assert r.concept == "geo"
    assert r.role_key == "reseau"


def test_concept_from_values_supplier_and_channel():
    supplier = resp.resolve("x", segment="Fournisseur Delta",
                            samples=["Fournisseur Alpha", "Fournisseur Beta"])
    assert supplier.concept == "supplier" and supplier.role_key == "supply"

    channel = resp.resolve("col_9", segment="Publicité payante",
                           samples=["Référencement", "Bouche-à-oreille", "Partenariats"])
    assert channel.concept == "channel" and channel.role_key == "canal"


def test_concept_from_values_department_and_segment():
    dept = resp.resolve("z", segment="Ingénierie",
                        samples=["Ventes", "Support", "Marketing"])
    assert dept.concept == "employee" and dept.role_key == "rh"

    seg = resp.resolve("q", segment="Particulier", samples=["Pro", "VIP"])
    assert seg.concept == "customer_segment" and seg.role_key == "crm"


def test_falls_back_to_name_when_values_are_opaque():
    """Valeurs non parlantes (« Composants ») : on peut aussi retomber sur le NOM."""
    # Valeur « Composants » = token produit → produit.
    by_value = resp.resolve("col_x", segment="Composants", samples=["Assemblage"])
    assert by_value.role_key == "produit"
    # Valeurs totalement opaques → fallback sur le nom de l'axe.
    by_name = resp.resolve("ligne_produit", segment="ABC", samples=["DEF", "GHI"])
    assert by_name.concept == "product" and by_name.role_key == "produit"


def test_unknown_when_nothing_matches():
    assert resp.resolve("col_1", segment="ABC", samples=["DEF", "GHI"]) is None
