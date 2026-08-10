"""Semantic Layer — traduit le langage physique du moteur en concepts métier.

La couche Decision ne doit jamais exposer le schéma physique : un dirigeant lit
« Le chiffre d'affaires recule de 8 % », pas « total de amount_ttc en baisse ».
Le physique (orders.amount_ttc, SUM, jointures) reste, lui, dans la Preuve.

Ce module s'applique en PRÉSENTATION, à la frontière de l'API : il enrichit le
dict d'investigation (concepts + lignage) et reformule les chaînes destinées à
l'utilisateur, sans toucher à l'état interne du moteur (le benchmark, qui lit
l'objet Investigation, reste inchangé).

Le vocabulaire vient d'un lexique métier (c'est le rôle d'une Semantic Layer) —
et non d'un `if column == "amount_ttc"` codé dans le frontend.
"""
from __future__ import annotations

import re

# --- Lexique métier : jetons physiques → concept ---------------------------
_REGION = ("region", "région", "regions")
_CITY = ("city", "ville", "villes")
_STORE = ("store", "shop", "magasin", "boutique", "pos")
_PRODUCT = ("product", "produit", "article", "item", "sku", "famille", "categorie", "catégorie", "category")
_SUPPLIER = ("supplier", "fournisseur", "vendor")
_CHANNEL = ("channel", "canal", "source")
_SEGMENT = ("segment", "tier", "categorie_client")
_DEPARTMENT = ("department", "departement", "département", "service", "equipe", "équipe", "team")
_CUSTOMER = ("customer", "client", "clients", "customers")
_EMPLOYEE = ("employee", "salarie", "salarié", "agent", "collaborateur")

# Domaines (table racine → intitulé d'analyse).
_DOMAINS = [
    (("order", "commande", "sale", "vente"), "Ventes"),
    (("customer", "client"), "Clients"),
    (("employee", "salarie", "rh", "hr", "staff"), "Ressources humaines"),
    (("invoice", "facture", "finance", "compta"), "Finance"),
    (("stock", "inventory", "supply", "appro"), "Supply chain"),
    (("product", "produit", "article"), "Catalogue"),
]

_MONEY = ("amount", "montant", "revenue", "ca", "chiffre", "price", "prix", "cost", "cout", "coût", "total", "mrr", "arr")
_TTC = ("ttc", "gross", "incl", "brut")
_HT = ("ht", "net", "excl", "hors")


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[_\W]+", (s or "").lower()) if t}


def _any(toks: set[str], hints) -> bool:
    return any(h in toks or any(h in t for t in toks) for h in hints)


def measure_concept(metric_label: str) -> str:
    """« total de amount_ttc » → « Chiffre d'affaires » ; « nombre de … » → volume."""
    low = (metric_label or "").lower()
    toks = _tokens(metric_label)
    if low.startswith("nombre") or "count" in toks:
        return "Nombre d'enregistrements"
    if _any(toks, _MONEY):
        if _any(toks, _HT) and not _any(toks, _TTC):
            return "Chiffre d'affaires (HT)"
        return "Chiffre d'affaires"
    if any(w in low for w in ("moyenne", "moyen", "avg")):
        return "Valeur moyenne"
    # À défaut : humaniser la dernière portion (sans préfixe « total de »).
    core = re.sub(r"^(total de|somme de|moyenne de)\s+", "", low).strip()
    return core[:1].upper() + core[1:] if core else (metric_label or "Mesure")


def _concept_for_tokens(toks: set[str]) -> str | None:
    if _any(toks, _REGION):
        return "Région"
    if _any(toks, _SEGMENT):
        return "Segment client"
    if _any(toks, _CITY):
        return "Ville"
    if _any(toks, _STORE):
        return "Magasin"
    if _any(toks, _SUPPLIER):
        return "Fournisseur"
    if _any(toks, _CHANNEL):
        return "Canal"
    if _any(toks, _DEPARTMENT):
        return "Département"
    if _any(toks, _PRODUCT):
        return "Produit"
    if _any(toks, _EMPLOYEE):
        return "Collaborateur"
    if _any(toks, _CUSTOMER):
        return "Client"
    return None


def dimension_concept(dim_label: str) -> tuple[str, str | None]:
    """« region (stores) » → (« Région », « stores.region »)."""
    physical = None
    inner = dim_label
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", dim_label or "")
    if m:
        inner, table = m.group(1).strip(), m.group(2).strip()
        col = inner.split()[-1] if inner else inner
        physical = f"{table}.{col}"
    label = _concept_for_tokens(_tokens(inner)) or (inner[:1].upper() + inner[1:] if inner else dim_label)
    return label, physical


def subject_domain(table: str) -> str:
    toks = _tokens(table)
    for hints, label in _DOMAINS:
        if _any(toks, hints):
            return label
    return (table[:1].upper() + table[1:]) if table else "Analyse"


def _walk_replace(node, repls: list[tuple[str, str]]):
    if isinstance(node, str):
        out = node
        for a, b in repls:
            if a and a in out:
                out = out.replace(a, b)
        return out
    if isinstance(node, list):
        return [_walk_replace(x, repls) for x in node]
    if isinstance(node, dict):
        return {k: _walk_replace(v, repls) for k, v in node.items()}
    return node


def translate(obj, repls: list[tuple[str, str]]):
    """Applique une liste de remplacements (physique → concept) à un objet."""
    return _walk_replace(obj, repls)


def apply_semantic_layer(inv: dict) -> list[tuple[str, str]]:
    """Enrichit et reformule un dict d'investigation en langage métier.

    Ajoute `subject_label`, `lineage` (physique, pour la Preuve) et `concepts`,
    puis remplace les libellés physiques par les concepts dans les chaînes
    destinées à l'utilisateur. Renvoie la liste des remplacements pour que
    l'appelant traduise aussi le message, les décisions, etc. Défensif.
    """
    if not isinstance(inv, dict):
        return []

    metric_label = inv.get("metric_label") or ""
    measure_lbl = measure_concept(metric_label)

    # Collecte des libellés de dimension présents dans l'investigation.
    dim_labels: set[str] = set()
    attr = inv.get("attribution") or {}
    for key in ("candidates", "drivers"):
        for c in attr.get(key) or []:
            if c.get("dimension"):
                dim_labels.add(c["dimension"])
    for c in inv.get("drivers_struct") or []:
        if c.get("dimension"):
            dim_labels.add(c["dimension"])
    if isinstance(inv.get("broad_based"), dict) and inv["broad_based"].get("dimension"):
        dim_labels.add(inv["broad_based"]["dimension"])

    lineage_dims = []
    repls: list[tuple[str, str]] = []
    for dl in dim_labels:
        concept, physical = dimension_concept(dl)
        repls.append((dl, concept))
        lineage_dims.append({"concept": concept, "physical": physical, "physical_label": dl})
    if metric_label:
        repls.append((metric_label, measure_lbl))
    # Remplacer les chaînes les plus longues d'abord (évite les recouvrements).
    repls.sort(key=lambda p: len(p[0]), reverse=True)

    # Reformuler les champs texte destinés à l'utilisateur.
    for field in ("conclusion",):
        if inv.get(field):
            inv[field] = _walk_replace(inv[field], repls)
    for field in ("steps", "key_drivers", "recommendations", "revisions"):
        if inv.get(field) is not None:
            inv[field] = _walk_replace(inv[field], repls)

    inv["subject_label"] = subject_domain(inv.get("subject") or "")
    inv["measure_label_concept"] = measure_lbl
    inv["lineage"] = {
        "measure": {"concept": measure_lbl, "physical_label": metric_label},
        "dimensions": lineage_dims,
    }
    inv["concepts"] = (
        [{"kind": "measure", "label": measure_lbl, "physical_label": metric_label}]
        + [{"kind": "dimension", "label": d["concept"], "physical": d["physical"]} for d in lineage_dims]
    )
    return repls
