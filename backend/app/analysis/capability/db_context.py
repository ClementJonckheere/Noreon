"""Phase 2 — C6/shadow : construction du VRAI ResolutionContext depuis la DB.

Règle #1 du câblage shadow : le resolver doit travailler sur le contexte RÉEL du
space/connection, pas un catalogue de test. On construit ENSEMBLE le
`PlannerCatalog` (donné au LLM) et le `ResolutionContext` (donné au resolver) à
partir de la MÊME source, avec des refs COHÉRENTES — sinon les refs du plan LLM
ne se résoudraient pas en C6.

Relations : uniquement system-validated (`status=validated` OU `origin=constraint`).
Le worker garde sa propre session (fournie par l'appelant). Best-effort : ce qui
manque devient `unresolved` en C6, jamais inventé.
"""
from __future__ import annotations

import re

from app.analysis.capability.adapter import normalize_cardinality
from app.analysis.capability.model import (
    ADD_FULL,
    Dimension,
    Entity,
    Measure,
    Relation,
    ResolutionContext,
    ResolutionPolicy,
)
from app.analysis.interpreter import PlannerCatalog

_NUMERIC = ("int", "float", "numeric", "double", "decimal", "real", "money", "serial")


def _tok(*parts: str) -> str:
    raw = "_".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9_]", "_", raw.lower()).strip("_") or "x"


def build_catalog_and_context(session, connection_id: int, *, tenant_id: int | None = None,
                              hidden_tables=None, hidden_columns=None):
    """Renvoie (PlannerCatalog, ResolutionContext) avec des refs IDENTIQUES, ou
    (None, None) si aucun schéma scanné."""
    from app.services.schema_context import current_snapshot

    snap = current_snapshot(session, connection_id)
    if snap is None or not snap.tables:
        return None, None

    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    hidden_columns = {(t.lower(), c.lower()) for t, c in (hidden_columns or set())}

    concepts_cat, metrics_cat, dims_cat = [], [], []
    entities, measures, dimensions = {}, {}, {}
    hidden_refs: set[str] = set()

    for t in snap.tables:
        tname = t.table_name
        ent_ref = f"concept:{_tok(tname)}"
        pk = tuple(c.name for c in (getattr(t, "columns", []) or []) if getattr(c, "is_primary_key", False))
        entities[ent_ref] = Entity(ref=ent_ref, grain_keys=pk, physical=tname)
        concepts_cat.append({"entity_ref": ent_ref, "entity_label": tname})
        table_hidden = tname.lower() in hidden_tables
        if table_hidden:
            hidden_refs.add(ent_ref)
        for c in getattr(t, "columns", []) or []:
            dt = (c.data_type or "").lower()
            ref_tok = _tok(tname, c.name)
            col_hidden = table_hidden or (tname.lower(), c.name.lower()) in hidden_columns
            if any(n in dt for n in _NUMERIC):
                ref = f"metric:{ref_tok}"
                measures[ref] = Measure(ref=ref, home_entity=ent_ref, additivity=ADD_FULL,
                                        physical=f"{tname}.{c.name}")
                metrics_cat.append({"metric_ref": ref, "metric_label": c.name})
            else:
                ref = f"dimension:{ref_tok}"
                dimensions[ref] = Dimension(ref=ref, home_entity=ent_ref, physical=f"{tname}.{c.name}")
                dims_cat.append({"dimension_ref": ref, "dimension_label": c.name})
            if col_hidden:
                hidden_refs.add(ref)

    relations, relations_cat = _load_relations(session, connection_id, tenant_id, _tok)

    catalog = PlannerCatalog(concepts=concepts_cat, metrics=metrics_cat, dimensions=dims_cat,
                             relations=relations_cat, stats={}, domain="")
    context = ResolutionContext(
        entities=entities, measures=measures, dimensions=dimensions, relations=tuple(relations),
        quality={}, freshness={}, access={"hidden": hidden_refs, "source_reachable": True},
        policy=ResolutionPolicy())
    return catalog, context


def _load_relations(session, connection_id, tenant_id, tok):
    """Relations system-validated depuis relation_candidate."""
    try:
        from app.models.relation_candidate import RelationCandidate
        from sqlalchemy import select
        q = select(RelationCandidate).where(RelationCandidate.connection_id == connection_id)
        rows = list(session.execute(q).scalars().all())
    except Exception:  # noqa: BLE001 - table absente / erreur : pas de relation (honnête)
        return [], []
    relations, cat = [], []
    for r in rows:
        validated = (getattr(r, "status", "") == "validated") or (getattr(r, "origin", "") == "constraint")
        if not validated:
            continue
        from_ent = f"concept:{tok(r.left_table)}"
        to_ent = f"concept:{tok(r.right_table)}"
        rel_ref = f"rel_{r.id}"
        relations.append(Relation(
            id=int(r.id), from_entity=from_ent, to_entity=to_ent,
            cardinality=normalize_cardinality(getattr(r, "cardinality", None)),
            from_key=f"{r.left_table}.{r.left_column}", to_key=f"{r.right_table}.{r.right_column}",
            status=getattr(r, "status", "candidate"), origin=getattr(r, "origin", "inferred"),
            coverage=getattr(r, "coverage", None), target_uniqueness=getattr(r, "target_uniqueness", None)))
        cat.append({"relation_ref": rel_ref, "cardinality": normalize_cardinality(getattr(r, "cardinality", None))})
    return relations, cat
