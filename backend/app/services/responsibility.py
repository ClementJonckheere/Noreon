"""Responsibility Engine — du CONCEPT métier au DÉCIDEUR.

Le Decision Engine ne devrait pas recevoir une colonne (« col_004 »), ni même son
nom, mais un **concept** : « zone géographique », « fournisseur », « canal »… Ce
composant détecte le concept à partir des **VALEURS** (et, à défaut, du nom de
l'axe), puis le mappe à une responsabilité métier.

    col_004  →  valeurs {Paris, Lille, Marseille, Nice}
             →  concept « zone géographique »
             →  Directeur réseau

Pipeline :  Reasoning Engine → Concepts → Responsibility Engine → Decision Engine.

Détecter par la valeur (et non par le nom) rend le routage **robuste aux colonnes
opaques** : même un axe nommé « a3 » est reconnu comme géographique si ses valeurs
sont des régions. C'est la suite logique de l'indépendance au nom de schéma (P-01).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Concepts métier -> décideur (clé de rôle du Decision Engine) -------------
CONCEPT_ROLE = {
    "geo": "reseau",
    "store": "reseau",
    "supplier": "supply",
    "channel": "canal",
    "employee": "rh",
    "customer_segment": "crm",
    "product": "produit",
    "time": None,            # la temporalité relève de la Direction (pas d'action ciblée)
}

CONCEPT_LABEL = {
    "geo": "zone géographique",
    "store": "point de vente",
    "supplier": "fournisseur",
    "channel": "canal",
    "employee": "équipe / département",
    "customer_segment": "segment client",
    "product": "gamme de produits",
    "time": "temps",
}

# --- Détection PAR LES VALEURS (indépendante du nom de la colonne) ------------
_FR_REGIONS = {
    "île-de-france", "ile-de-france", "provence-alpes-côte d'azur",
    "provence-alpes-cote d'azur", "auvergne-rhône-alpes", "auvergne-rhone-alpes",
    "hauts-de-france", "nouvelle-aquitaine", "occitanie", "grand est", "bretagne",
    "normandie", "pays de la loire", "bourgogne-franche-comté", "centre-val de loire",
    "corse", "paca",
}
_FR_CITIES = {
    "paris", "lyon", "marseille", "lille", "nice", "bordeaux", "nantes",
    "strasbourg", "toulouse", "montpellier", "rennes", "reims", "toulon",
    "grenoble", "dijon", "angers", "clermont-ferrand",
}
# Tokens distinctifs (recherche en sous-chaîne).
_SUPPLIER_TOK = ("fournisseur", "supplier", "vendor")
_CHANNEL_TOK = ("publicité", "publicite", "payante", "référencement", "referencement",
                "bouche-à-oreille", "bouche-a-oreille", "partenariat", "paypal",
                "virement", "affiliation", "organic", "adwords")
# Ensembles exacts (évite les faux positifs sur des mots courants).
_DEPT_SET = {"ingénierie", "ingenierie", "ventes", "marketing", "support", "finance",
             "commercial", "production", "logistique", "r&d", "rh"}
_SEGMENT_SET = {"particulier", "particuliers", "professionnel", "pro", "vip",
                "premium", "standard", "entreprise", "b2b", "b2c", "grand compte"}
_PRODUCT_TOK = ("composants", "assemblage", "maintenance", "textile", "high-tech",
                "électronique", "electronique", "alimentaire", "gamme", "déco")

# --- Fallback PAR LE NOM de l'axe (quand les valeurs ne parlent pas) ----------
_NAME_CONCEPT = [
    ("supplier", r"fournisseur|supplier|entrep|warehouse|appro|logisti|transport|livraison|rupture"),
    ("employee", r"departement|département|employ|salari|effectif|motif|poste|turnover|équipe|equipe|manager|démission|demission"),
    ("geo", r"region|région|zone|secteur|territoire|ville|city|pays|country"),
    ("store", r"magasin|store|shop|boutique|point de vente|pdv"),
    ("channel", r"paiement|payment|canal|channel|method|mode|acquisition"),
    ("product", r"produit|product|categor|catégor|gamme|article|référence|ligne_produit|sku"),
    ("customer_segment", r"client|customer|fidel|fidél|loyal|genre|segment|acheteur|âge|age\b"),
    ("time", r"mois|date|month|trimestre|semaine|jour|périod|period"),
]


@dataclass
class Responsibility:
    concept: str          # geo | supplier | channel | …
    concept_label: str    # « zone géographique »
    role_key: str | None  # clé de rôle du Decision Engine (None = Direction)


def _concept_from_values(values: list[str]) -> str | None:
    low = [str(v).strip().lower() for v in values if v is not None and str(v).strip()]
    if not low:
        return None
    if any(v in _FR_REGIONS for v in low):
        return "geo"
    if any(v in _FR_CITIES for v in low):
        return "store"
    if any(any(tok in v for tok in _SUPPLIER_TOK) for v in low):
        return "supplier"
    if any(any(tok in v for tok in _CHANNEL_TOK) for v in low):
        return "channel"
    if any(v in _DEPT_SET for v in low):
        return "employee"
    if any(v in _SEGMENT_SET for v in low):
        return "customer_segment"
    if any(any(tok in v for tok in _PRODUCT_TOK) for v in low):
        return "product"
    return None


def _concept_from_name(dimension_label: str) -> str | None:
    low = (dimension_label or "").lower()
    for concept, pat in _NAME_CONCEPT:
        if re.search(pat, low):
            return concept
    return None


def resolve(dimension_label: str, segment: str | None = None,
            samples: list[str] | None = None) -> Responsibility | None:
    """Concept + décideur pour un axe, PAR LES VALEURS d'abord, le NOM ensuite."""
    values = ([segment] if segment else []) + list(samples or [])
    concept = _concept_from_values(values) or _concept_from_name(dimension_label)
    if concept is None:
        return None
    return Responsibility(concept=concept,
                          concept_label=CONCEPT_LABEL.get(concept, concept),
                          role_key=CONCEPT_ROLE.get(concept))
