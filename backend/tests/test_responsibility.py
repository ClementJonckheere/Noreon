"""Responsibility Engine — GÉNÉRIQUE, piloté par le BusinessContext.

Le routage ne dépend d'aucun vocabulaire codé dans le moteur : c'est le CONTEXTE
DÉCLARÉ (ici la fixture Démo Retail) qui apporte les ensembles de valeurs et les
rôles. Sans contexte (organisation inconnue), `resolve` renvoie toujours None —
et le moteur bascule sur des recommandations génériques.
"""
from __future__ import annotations

from app.fixtures import demo_retail
from app.services import responsibility as resp
from app.services.business_context import EMPTY

RETAIL = demo_retail.context()


def test_concept_from_values_geography_even_when_name_is_opaque():
    """Colonne opaque « a3 » mais valeurs = régions → zone géographique → réseau."""
    r = resp.resolve(RETAIL, "a3", segment="Provence-Alpes-Côte d'Azur",
                     samples=["Île-de-France", "Auvergne-Rhône-Alpes", "Hauts-de-France"])
    assert r is not None
    assert r.concept_key == "geo"
    assert r.actor_label == "Directeur réseau"


def test_concept_from_values_supplier_and_channel():
    supplier = resp.resolve(RETAIL, "x", segment="Fournisseur Delta",
                            samples=["Fournisseur Alpha", "Fournisseur Beta"])
    assert supplier.concept_key == "supplier" and supplier.actor_label == "Directeur supply chain"

    channel = resp.resolve(RETAIL, "col_9", segment="Publicité payante",
                           samples=["Référencement", "Bouche-à-oreille", "Partenariats"])
    assert channel.concept_key == "channel" and channel.actor_label == "Responsable des opérations"


def test_concept_from_values_department_and_segment():
    dept = resp.resolve(RETAIL, "z", segment="Ingénierie",
                        samples=["Ventes", "Support", "Marketing"])
    assert dept.concept_key == "employee" and dept.actor_label == "Directeur des ressources humaines"

    seg = resp.resolve(RETAIL, "q", segment="Particulier", samples=["Pro", "VIP"])
    assert seg.concept_key == "customer_segment" and seg.actor_label == "Responsable CRM"


def test_falls_back_to_name_when_values_are_opaque():
    """Valeurs non parlantes : on peut aussi retomber sur le NOM de l'axe."""
    by_value = resp.resolve(RETAIL, "col_x", segment="Composants", samples=["Assemblage"])
    assert by_value.actor_label == "Directeur produit"
    by_name = resp.resolve(RETAIL, "ligne_produit", segment="ABC", samples=["DEF", "GHI"])
    assert by_name.concept_key == "product" and by_name.actor_label == "Directeur produit"


def test_unknown_when_nothing_matches():
    assert resp.resolve(RETAIL, "col_1", segment="ABC", samples=["DEF", "GHI"]) is None


def test_empty_context_never_resolves():
    """Sans contexte déclaré (entrepreneur solo), aucun responsable n'est jamais
    inventé — même sur des valeurs qui « ressembleraient » à des régions."""
    assert resp.resolve(EMPTY, "a3", segment="Provence-Alpes-Côte d'Azur",
                        samples=["Île-de-France"]) is None
