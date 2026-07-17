"""Moteur de compréhension métier (Module 5) — agent Sémantique.

Identifie les concepts métier à partir des NOMS et du CONTENU RÉEL des
colonnes (profils : PII, types détectés, statistiques), et propose des
mappings concept ↔ colonne avec un niveau de confiance.

Règles fondamentales (cahier des charges) :
- Statut « proposé », JAMAIS auto-validé : l'humain valide, corrige ou rejette.
- Les corrections alimentent la mémoire entreprise : un mapping rejeté n'est
  pas re-proposé ; un mapping validé/corrigé est conservé tel quel.
- Variantes sémantiques piégeuses (net_price HT vs amount_ttc TTC) :
  arbitrage demandé, jamais de fusion silencieuse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.semantic import BusinessConcept, ConceptMapping

log = get_logger("noreon.semantic")

# ---------------------------------------------------------------------------
# Lexique de concepts (FR/EN) — indices par NOM de colonne/table
# ---------------------------------------------------------------------------
CONCEPT_LEXICON: dict[str, dict] = {
    "Client": {
        "description": "Personne ou organisation cliente de l'entreprise.",
        "name_hints": ["customer", "client", "cust", "buyer", "acheteur", "compte"],
        "table_hints": ["customers", "clients", "accounts"],
    },
    "Produit": {
        "description": "Article ou service vendu.",
        "name_hints": ["product", "produit", "article", "item", "sku"],
        "table_hints": ["products", "produits", "articles", "items"],
    },
    "Commande": {
        "description": "Commande ou transaction de vente.",
        "name_hints": ["order", "commande", "purchase", "vente", "sale"],
        "table_hints": ["orders", "commandes", "sales", "ventes"],
    },
    "Montant": {
        "description": "Valeur monétaire (prix, total, montant).",
        "name_hints": ["amount", "price", "total", "montant", "prix", "cost", "revenue", "ca"],
        "numeric_only": True,
    },
    "Quantité": {
        "description": "Nombre d'unités.",
        "name_hints": ["quantity", "qty", "quantite", "nombre", "count", "units"],
        "numeric_only": True,
    },
    "Magasin": {
        "description": "Point de vente physique ou en ligne.",
        "name_hints": ["store", "shop", "magasin", "boutique", "pos"],
        "table_hints": ["stores", "magasins", "shops"],
    },
    "Paiement": {
        "description": "Règlement d'une commande.",
        "name_hints": ["payment", "paiement", "reglement", "paid"],
        "table_hints": ["payments", "paiements"],
    },
    "Email": {
        "description": "Adresse électronique.",
        "name_hints": ["email", "mail", "courriel"],
        "pii": "email",
    },
    "Téléphone": {
        "description": "Numéro de téléphone.",
        "name_hints": ["phone", "tel", "telephone", "mobile"],
        "pii": "phone",
    },
    "Nom": {
        "description": "Nom d'une personne ou d'une entité.",
        "name_hints": ["name", "nom", "prenom", "firstname", "lastname", "full_name"],
        "pii": "name",
    },
    "Date": {
        "description": "Repère temporel (commande, inscription, paiement…).",
        "name_hints": ["date", "_at", "created", "updated", "signup", "paid_at", "jour"],
        "temporal": True,
    },
    "Localisation": {
        "description": "Ville, région, adresse.",
        "name_hints": ["city", "ville", "region", "address", "adresse", "country", "pays", "zip", "postal"],
    },
    "Identifiant": {
        "description": "Clé technique d'identification.",
        "name_hints": [],  # traité par règle PK/suffixe id
    },
}

# Variantes piégeuses de montants : HT vs TTC (arbitrage obligatoire).
_HT_MARKERS = ("net", "ht", "excl", "hors_taxe", "horstaxe")
_TTC_MARKERS = ("ttc", "gross", "incl", "brut")


@dataclass
class Proposal:
    concept_name: str
    schema_name: str
    table_name: str
    column_name: str
    confidence: float
    rationale: str
    needs_arbitration: bool = False
    arbitration_note: str | None = None


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", name.lower()) if t]


def _match_hint(name: str, hints: list[str]) -> str | None:
    low = name.lower()
    toks = set(_tokens(name))
    for h in hints:
        if h.startswith("_"):  # suffixe (ex. _at)
            if low.endswith(h):
                return h
        elif h in toks:
            return h
        elif len(h) >= 4 and h in low:
            return h
    return None


def _is_numeric_profile(p: ColumnProfile) -> bool:
    dt = (p.detected_type or "").lower()
    return dt.startswith(("integer", "numeric")) and "texte" not in dt or dt in ("integer", "numeric")


def _is_temporal_profile(p: ColumnProfile) -> bool:
    return (p.detected_type or "").startswith("datetime")


def _amount_variant(column_name: str) -> str | None:
    """Renvoie 'HT', 'TTC' ou None selon les marqueurs du nom de colonne."""
    toks = set(_tokens(column_name))
    low = column_name.lower()
    if toks & set(_HT_MARKERS) or any(m in low for m in ("net_", "_ht")):
        return "HT"
    if toks & set(_TTC_MARKERS) or "_ttc" in low or "ttc" in toks:
        return "TTC"
    return None


def generate_proposals(profiles: list[ColumnProfile]) -> list[Proposal]:
    """Propose des mappings concept ↔ colonne à partir des noms ET du contenu."""
    proposals: list[Proposal] = []
    amount_columns: list[tuple[Proposal, str | None]] = []

    for p in profiles:
        col = p.column_name
        best: Proposal | None = None

        for concept, spec in CONCEPT_LEXICON.items():
            confidence = 0.0
            reasons: list[str] = []

            # 1) Contenu réel (le plus fiable) : PII et types détectés au profilage.
            if spec.get("pii") and p.pii_type == spec["pii"]:
                confidence = max(confidence, 0.9)
                reasons.append(f"le contenu réel est détecté comme {spec['pii']} (profilage)")
            if spec.get("temporal") and _is_temporal_profile(p):
                confidence = max(confidence, 0.75)
                reasons.append("le contenu réel est temporel (profilage)")

            # 2) Nom de colonne.
            hint = _match_hint(col, spec.get("name_hints", []))
            if hint:
                # numeric_only : un « amount » non numérique n'est pas un Montant.
                if spec.get("numeric_only") and not _is_numeric_profile(p):
                    reasons.append(f"nom évocateur ({hint}) mais contenu non numérique — écarté")
                else:
                    confidence = max(confidence, 0.85 if confidence >= 0.7 else 0.7)
                    reasons.append(f"nom de colonne évocateur (« {hint} »)")

            # 3) Nom de table (le concept-entité porte sur la table entière,
            # on le rattache à sa clé primaire probable).
            table_hint = _match_hint(p.table_name, spec.get("table_hints", []))
            if table_hint and col in ("id", f"{p.table_name.rstrip('s')}_id"):
                confidence = max(confidence, 0.8)
                reasons.append(f"clé primaire de la table « {p.table_name} » (concept-entité)")

            if confidence > 0 and (best is None or confidence > best.confidence):
                best = Proposal(
                    concept_name=concept,
                    schema_name=p.schema_name,
                    table_name=p.table_name,
                    column_name=col,
                    confidence=round(confidence, 2),
                    rationale=" ; ".join(reasons),
                )

        if best is None:
            continue

        # Détection des variantes piégeuses de Montant (HT vs TTC).
        if best.concept_name == "Montant":
            amount_columns.append((best, _amount_variant(col)))
        proposals.append(best)

    # Arbitrage HT/TTC : si des montants de variantes différentes coexistent,
    # chacun est marqué « arbitrage requis » — jamais de fusion silencieuse.
    variants = {v for _, v in amount_columns if v}
    if len(variants) > 1 or (len(variants) == 1 and any(v is None for _, v in amount_columns)):
        cols_desc = ", ".join(
            f"{pr.table_name}.{pr.column_name} ({v or 'variante inconnue'})"
            for pr, v in amount_columns
        )
        for pr, v in amount_columns:
            pr.needs_arbitration = True
            pr.arbitration_note = (
                f"Plusieurs variantes de montant détectées : {cols_desc}. "
                "Un montant HT et un montant TTC ne sont pas équivalents — "
                "validez chaque colonne en précisant sa nature avant de les utiliser ensemble."
            )

    return proposals


# ---------------------------------------------------------------------------
# Persistance + mémoire entreprise
# ---------------------------------------------------------------------------
def _get_or_create_concept(db: Session, tenant_id: int, name: str) -> BusinessConcept:
    concept = db.execute(
        select(BusinessConcept).where(
            BusinessConcept.tenant_id == tenant_id, BusinessConcept.name == name
        )
    ).scalar_one_or_none()
    if concept is None:
        spec = CONCEPT_LEXICON.get(name, {})
        concept = BusinessConcept(
            tenant_id=tenant_id,
            name=name,
            description=spec.get("description", ""),
            synonyms=list(spec.get("name_hints", [])),
            origin="system" if name in CONCEPT_LEXICON else "user",
        )
        db.add(concept)
        db.flush()
    return concept


def propose_and_persist(db: Session, conn: Connection) -> dict:
    """Génère les propositions et les persiste en respectant la mémoire.

    - Un mapping déjà validé/corrigé/rejeté n'est JAMAIS écrasé (mémoire
      entreprise : les décisions humaines priment).
    - Un mapping déjà proposé est mis à jour (confiance/justification).
    """
    profiles = db.execute(
        select(ColumnProfile).where(ColumnProfile.connection_id == conn.id)
    ).scalars().all()
    if not profiles:
        raise ValueError("Aucun profil de colonne — lancez un profilage avant l'analyse sémantique.")

    proposals = generate_proposals(profiles)

    existing = db.execute(
        select(ConceptMapping).where(ConceptMapping.connection_id == conn.id)
    ).scalars().all()
    by_column: dict[tuple[str, str, str], list[ConceptMapping]] = {}
    for m in existing:
        by_column.setdefault((m.schema_name, m.table_name, m.column_name), []).append(m)

    created, updated, skipped = 0, 0, 0
    for pr in proposals:
        key = (pr.schema_name, pr.table_name, pr.column_name)
        col_mappings = by_column.get(key, [])

        # Mémoire entreprise : décision humaine existante sur cette colonne → on ne touche pas.
        if any(m.status in ("validated", "corrected", "rejected") for m in col_mappings):
            skipped += 1
            continue

        concept = _get_or_create_concept(db, conn.tenant_id, pr.concept_name)
        same = next((m for m in col_mappings if m.concept_id == concept.id), None)
        if same is not None:
            same.confidence = pr.confidence
            same.rationale = pr.rationale
            same.needs_arbitration = pr.needs_arbitration
            same.arbitration_note = pr.arbitration_note
            updated += 1
        else:
            # Une proposition remplace l'ancienne proposition (concept différent).
            for m in col_mappings:
                if m.status == "proposed":
                    db.delete(m)
            db.add(ConceptMapping(
                tenant_id=conn.tenant_id,
                connection_id=conn.id,
                concept_id=concept.id,
                schema_name=pr.schema_name,
                table_name=pr.table_name,
                column_name=pr.column_name,
                confidence=pr.confidence,
                rationale=pr.rationale,
                status="proposed",
                needs_arbitration=pr.needs_arbitration,
                arbitration_note=pr.arbitration_note,
            ))
            created += 1

    db.flush()
    return {
        "proposed": created,
        "updated": updated,
        "kept_human_decisions": skipped,
        "arbitrations_needed": sum(1 for p in proposals if p.needs_arbitration),
    }


def validated_concepts_context(db: Session, connection_id: int) -> tuple[str, dict[str, set[str]]]:
    """Contexte « dictionnaire métier » pour le moteur SQL.

    Renvoie (texte lisible pour le LLM, {nom_table: {synonymes}}) construit à
    partir des mappings VALIDÉS/CORRIGÉS uniquement — les propositions non
    validées ne deviennent pas des vérités.
    """
    rows = db.execute(
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(
            ConceptMapping.connection_id == connection_id,
            ConceptMapping.status.in_(["validated", "corrected"]),
        )
    ).all()
    if not rows:
        return "", {}

    lines = ["", "Dictionnaire métier validé :"]
    table_synonyms: dict[str, set[str]] = {}
    by_concept: dict[str, list[ConceptMapping]] = {}
    concept_syns: dict[str, list[str]] = {}
    for m, c in rows:
        by_concept.setdefault(c.name, []).append(m)
        concept_syns[c.name] = c.synonyms or []

    for cname, mappings in sorted(by_concept.items()):
        cols = ", ".join(f"{m.table_name}.{m.column_name}" for m in mappings)
        lines.append(f"  Concept {cname} = {cols}")
        for m in mappings:
            syns = table_synonyms.setdefault(m.table_name, set())
            syns.add(cname.lower())
            syns.update(s.lower() for s in concept_syns.get(cname, []))
    return "\n".join(lines), table_synonyms
