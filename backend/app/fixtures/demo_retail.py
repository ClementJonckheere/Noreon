"""Fixture « Démo Retail » — le BusinessContext DÉCLARÉ du scénario vitrine.

Tout le vocabulaire retail (régions, villes, gammes, rôles, actions-types) vit ici
et NULLE PART ailleurs dans le moteur. Un tenant qui déclare utiliser cette fixture
(`preferences.business_context = "demo_retail"`) obtient des recommandations
personnalisées par rôle ; sans elle, le moteur reste 100 % générique.

C'est le seul endroit du produit où « Directeur réseau », « PACA » ou « gamme »
ont le droit d'exister.
"""
from __future__ import annotations

from app.services.business_context import (
    Actor,
    BusinessContext,
    Origin,
    Responsibility,
    ResponsibilityMatcher,
)

# --- Détection PAR LES VALEURS (indépendante du nom de la colonne) ------------
_FR_REGIONS = frozenset({
    "île-de-france", "ile-de-france", "provence-alpes-côte d'azur",
    "provence-alpes-cote d'azur", "auvergne-rhône-alpes", "auvergne-rhone-alpes",
    "hauts-de-france", "nouvelle-aquitaine", "occitanie", "grand est", "bretagne",
    "normandie", "pays de la loire", "bourgogne-franche-comté", "centre-val de loire",
    "corse", "paca",
})
_FR_CITIES = frozenset({
    "paris", "lyon", "marseille", "lille", "nice", "bordeaux", "nantes",
    "strasbourg", "toulouse", "montpellier", "rennes", "reims", "toulon",
    "grenoble", "dijon", "angers", "clermont-ferrand",
})
_SUPPLIER_TOK = ("fournisseur", "supplier", "vendor")
_CHANNEL_TOK = ("publicité", "publicite", "payante", "référencement", "referencement",
                "bouche-à-oreille", "bouche-a-oreille", "partenariat", "paypal",
                "virement", "affiliation", "organic", "adwords")
_DEPT_SET = frozenset({"ingénierie", "ingenierie", "ventes", "marketing", "support",
                       "finance", "commercial", "production", "logistique", "r&d", "rh"})
_SEGMENT_SET = frozenset({"particulier", "particuliers", "professionnel", "pro", "vip",
                          "premium", "standard", "entreprise", "b2b", "b2c", "grand compte"})
_PRODUCT_TOK = ("composants", "assemblage", "maintenance", "textile", "high-tech",
                "électronique", "electronique", "alimentaire", "gamme", "déco")


def context() -> BusinessContext:
    """Le contexte retail seedé : acteurs (rôles) + responsabilités (concept →
    décideur → action-type). Les gabarits d'action utilisent {seg}, {dim}, {share}."""
    return BusinessContext(
        actors=[
            Actor(id="finance", label="Directeur financier"),
            Actor(id="reseau", label="Directeur réseau"),
            Actor(id="crm", label="Responsable CRM"),
            Actor(id="produit", label="Directeur produit"),
            Actor(id="canal", label="Responsable des opérations"),
            Actor(id="supply", label="Directeur supply chain"),
            Actor(id="rh", label="Directeur des ressources humaines"),
        ],
        responsibilities=[
            # Ordre = précédence de détection par les valeurs (régions avant villes…).
            Responsibility(
                concept_key="geo", concept_label="zone géographique",
                actor_label="Directeur réseau",
                action_template=("Auditer localement « {seg} » : conditions du point de "
                                 "vente, concurrence, exécution terrain."),
                justification_template="{share:.0f}% de la variation provient de « {seg} » ({dim}).",
                effort="Moyen",
                matcher=ResponsibilityMatcher(
                    value_set=_FR_REGIONS,
                    name_pattern=r"region|région|zone|secteur|territoire|ville|city|pays|country"),
            ),
            Responsibility(
                concept_key="store", concept_label="point de vente",
                actor_label="Directeur réseau",
                action_template=("Auditer localement « {seg} » : conditions du point de "
                                 "vente, concurrence, exécution terrain."),
                justification_template="{share:.0f}% de la variation provient de « {seg} » ({dim}).",
                effort="Moyen",
                matcher=ResponsibilityMatcher(
                    value_set=_FR_CITIES,
                    name_pattern=r"magasin|store|shop|boutique|point de vente|pdv"),
            ),
            Responsibility(
                concept_key="supplier", concept_label="fournisseur",
                actor_label="Directeur supply chain",
                action_template=("Sécuriser l'approvisionnement lié à « {seg} » : sourcing "
                                 "alternatif, stock de sécurité, pénalités de délai."),
                justification_template="« {seg} » concentre {share:.0f}% de la variation ({dim}).",
                effort="Moyen",
                matcher=ResponsibilityMatcher(
                    value_tokens=_SUPPLIER_TOK,
                    name_pattern=r"fournisseur|supplier|entrep|warehouse|appro|logisti|transport|livraison|rupture"),
            ),
            Responsibility(
                concept_key="channel", concept_label="canal",
                actor_label="Responsable des opérations",
                action_template="Analyser le parcours sur le canal « {seg} » (friction, coût, conversion).",
                justification_template="le canal « {seg} » explique {share:.0f}% de la variation ({dim}).",
                effort="Moyen",
                matcher=ResponsibilityMatcher(
                    value_tokens=_CHANNEL_TOK,
                    name_pattern=r"paiement|payment|canal|channel|method|mode|acquisition"),
            ),
            Responsibility(
                concept_key="employee", concept_label="équipe / département",
                actor_label="Directeur des ressources humaines",
                action_template=("Lancer un plan de rétention ciblé sur « {seg} » : entretiens, "
                                 "charge de travail, rémunération, perspectives de mobilité."),
                justification_template="« {seg} » concentre {share:.0f}% de la variation ({dim}).",
                effort="Moyen",
                matcher=ResponsibilityMatcher(
                    value_set=_DEPT_SET,
                    name_pattern=r"departement|département|employ|salari|effectif|motif|poste|turnover|équipe|equipe|manager|démission|demission"),
            ),
            Responsibility(
                concept_key="customer_segment", concept_label="segment client",
                actor_label="Responsable CRM",
                action_template=("Lancer une campagne de réactivation ciblée sur « {seg} » ; "
                                 "mesurer l'effet sur la fréquence d'achat."),
                justification_template="le segment client « {seg} » porte {share:.0f}% de la variation ({dim}).",
                effort="Faible",
                matcher=ResponsibilityMatcher(
                    value_set=_SEGMENT_SET,
                    name_pattern=r"client|customer|fidel|fidél|loyal|genre|segment|acheteur|âge|age\b"),
            ),
            Responsibility(
                concept_key="product", concept_label="gamme de produits",
                actor_label="Directeur produit",
                action_template="Revoir l'assortiment et le prix de la gamme « {seg} » ; vérifier les ruptures.",
                justification_template="la gamme « {seg} » pèse {share:.0f}% de la variation ({dim}).",
                effort="Élevé",
                matcher=ResponsibilityMatcher(
                    value_tokens=_PRODUCT_TOK,
                    name_pattern=r"produit|product|categor|catégor|gamme|article|référence|ligne_produit|sku"),
            ),
            # Temps : reconnu mais SANS action dédiée (la temporalité relève de la
            # Direction) → aucune décision émise, ni générique.
            Responsibility(
                concept_key="time", concept_label="temps", actor_label=None,
                action_template="",
                matcher=ResponsibilityMatcher(
                    name_pattern=r"mois|date|month|trimestre|semaine|jour|périod|period"),
            ),
        ],
    )
