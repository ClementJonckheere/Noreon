"""Routes de la compréhension métier (Module 5) : boucle de validation humaine.

Noreon propose, l'humain valide/corrige/rejette. Les décisions alimentent la
mémoire entreprise et sont réutilisées dans toutes les analyses suivantes.
Le dictionnaire est exportable (CSV/JSON) : livrable de documentation.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_tenant, get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.connection import Connection
from app.models.concept_definition import ConceptDefinition
from app.models.semantic import BusinessConcept, ConceptMapping
from app.models.tenant import Tenant
from app.schemas import (
    ConceptCreateIn,
    ConceptMappingOut,
    ConceptOut,
    MappingReviewIn,
    SemanticProposeOut,
)
from app.services import semantic as semantic_svc

router = APIRouter(prefix="/connections/{connection_id}/semantic", tags=["semantic"])
concepts_router = APIRouter(prefix="/concepts", tags=["semantic"])


@router.post("/propose", response_model=SemanticProposeOut,
             dependencies=[Depends(require_analyst)])
def propose(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> SemanticProposeOut:
    try:
        summary = semantic_svc.propose_and_persist(db, conn)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return SemanticProposeOut(**summary)


def _mapping_out(m: ConceptMapping, c: BusinessConcept) -> ConceptMappingOut:
    return ConceptMappingOut(
        id=m.id, concept_name=c.name, concept_description=c.description,
        schema_name=m.schema_name, table_name=m.table_name, column_name=m.column_name,
        confidence=m.confidence, analytical_roles=list(m.analytical_roles or []),
        rationale=m.rationale, status=m.status,
        needs_arbitration=m.needs_arbitration, arbitration_note=m.arbitration_note,
        review_note=m.review_note, reviewed_at=m.reviewed_at,
    )


@router.get("", response_model=list[ConceptMappingOut])
def list_mappings(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
) -> list[ConceptMappingOut]:
    stmt = (
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(ConceptMapping.connection_id == conn.id)
    )
    if status:
        stmt = stmt.where(ConceptMapping.status == status)
    rows = db.execute(
        stmt.order_by(ConceptMapping.table_name, ConceptMapping.column_name)
    ).all()
    return [_mapping_out(m, c) for m, c in rows]


@router.post("/{mapping_id}/review", response_model=ConceptMappingOut,
             dependencies=[Depends(require_analyst)])
def review_mapping(
    mapping_id: int,
    payload: MappingReviewIn,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> ConceptMappingOut:
    """Boucle de validation humaine : valider / corriger / rejeter."""
    mapping = db.get(ConceptMapping, mapping_id)
    if mapping is None or mapping.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Proposition introuvable.")

    now = datetime.now(timezone.utc)
    if payload.action == "validate":
        mapping.status = "validated"
        mapping.needs_arbitration = False
    elif payload.action == "reject":
        mapping.status = "rejected"
    elif payload.action == "correct":
        if not payload.concept_name:
            raise HTTPException(status_code=422, detail="concept_name requis pour une correction.")
        concept = semantic_svc._get_or_create_concept(db, conn.tenant_id, payload.concept_name)
        # Mémoire entreprise : la correction enrichit les synonymes du concept
        # (le nom de la colonne corrigée devient un indice réutilisable).
        syns = set(concept.synonyms or [])
        syns.add(mapping.column_name.lower())
        concept.synonyms = sorted(syns)
        mapping.concept_id = concept.id
        mapping.status = "corrected"
        mapping.needs_arbitration = False

    if payload.action in {"validate", "correct"} and payload.analytical_roles is not None:
        mapping.analytical_roles = list(dict.fromkeys(payload.analytical_roles))

    mapping.reviewed_at = now
    mapping.reviewed_by = "user"
    mapping.review_note = payload.note
    db.commit()
    db.refresh(mapping)
    concept = db.get(BusinessConcept, mapping.concept_id)
    return _mapping_out(mapping, concept)


@router.get("/export")
def export_dictionary(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Export du dictionnaire métier (CSV/JSON) — livrable de documentation."""
    rows = db.execute(
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.status != "rejected",
        )
        .order_by(BusinessConcept.name, ConceptMapping.table_name)
    ).all()
    data = [
        {
            "concept": c.name,
            "description": c.description,
            "synonymes": ";".join(c.synonyms or []),
            "schema": m.schema_name,
            "table": m.table_name,
            "colonne": m.column_name,
            "statut": m.status,
            "confiance": m.confidence,
            "roles_analytiques": ";".join(m.analytical_roles or []),
            "justification": m.rationale,
        }
        for m, c in rows
    ]
    if format == "json":
        return data
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()) if data else ["concept"])
    writer.writeheader()
    writer.writerows(data)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dictionnaire_metier.csv"},
    )


# ---- Concepts (tenant) : création manuelle + synonymes propres à l'entreprise ----
@concepts_router.get("", response_model=list[ConceptOut])
def list_concepts(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[ConceptOut]:
    rows = db.execute(
        select(BusinessConcept).where(BusinessConcept.tenant_id == tenant.id)
        .order_by(BusinessConcept.name)
    ).scalars().all()
    return [ConceptOut.model_validate(r) for r in rows]


@concepts_router.post("", response_model=ConceptOut, status_code=201,
             dependencies=[Depends(require_analyst)])
def create_concept(
    payload: ConceptCreateIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> ConceptOut:
    existing = db.execute(
        select(BusinessConcept).where(
            BusinessConcept.tenant_id == tenant.id, BusinessConcept.name == payload.name
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Fusion des synonymes plutôt que doublon.
        existing.synonyms = sorted(set(existing.synonyms or []) | {s.lower() for s in payload.synonyms})
        if payload.description:
            existing.description = payload.description
        db.commit()
        db.refresh(existing)
        return ConceptOut.model_validate(existing)
    concept = BusinessConcept(
        tenant_id=tenant.id, name=payload.name, description=payload.description,
        synonyms=[s.lower() for s in payload.synonyms], origin="user",
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)
    return ConceptOut.model_validate(concept)


# ---- Arbitrage GÉNÉRIQUE des concepts (aucune fixture métier dans l'API) --------
# Le concept est l'objet manipulé : « Magasin actif », « Client actif »… ne sont
# que des données seedées. L'état d'un concept est DÉRIVÉ (rule 5) :
#   validated | proposed | needs_arbitration ; « sans source » est un état SÉPARÉ
#   (absence de donnée ≠ ambiguïté de définition).
def _concept_status(db: Session, concept: BusinessConcept, space_id: int | None) -> str:
    from app.services import arbitration
    live = arbitration.definitions_of(db, concept.id, space_id=space_id)
    if len(live) >= 2:
        return "needs_arbitration"
    if any(d.is_reference for d in live):
        return "validated"
    if len(live) == 1:
        return "proposed"
    # Aucune définition : distinguer « proposé mais non défini » de « sans source ».
    has_mapping = db.execute(
        select(ConceptMapping.id).where(ConceptMapping.concept_id == concept.id).limit(1)
    ).scalar_one_or_none() is not None
    return "proposed" if has_mapping else "sans_source"


def _concept_overview(db: Session, concept: BusinessConcept, space_id: int | None = None) -> dict:
    from app.services import arbitration
    live = arbitration.definitions_of(db, concept.id, space_id=space_id)
    ref = next((d for d in live if d.is_reference), None)
    return {
        "id": concept.id, "name": concept.name, "description": concept.description,
        "status": _concept_status(db, concept, space_id),
        "definition_count": len(live),
        "reference_label": ref.label if ref else None,
        "reference_version": ref.definition_version if ref else None,
        # « space » = ce concept est SURCHARGÉ dans l'espace courant ; « universe » =
        # hérité de la définition commune de l'Univers.
        "scope_type": arbitration.effective_scope(db, concept.id, space_id),
    }


@concepts_router.get("/overview")
def concepts_overview(
    space_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[dict]:
    """Liste enrichie pour l'écran Concepts : statut dérivé + résumé des définitions.
    Résolu pour l'espace courant : définition héritée de l'Univers ou surchargée."""
    rows = db.execute(
        select(BusinessConcept).where(BusinessConcept.tenant_id == tenant.id)
        .order_by(BusinessConcept.name)
    ).scalars().all()
    return [_concept_overview(db, c, space_id) for c in rows]


def _owned_concept(db: Session, concept_id: int, tenant: Tenant) -> BusinessConcept:
    c = db.get(BusinessConcept, concept_id)
    if c is None or c.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Concept introuvable.")
    return c


def _definition_dict(db: Session, d) -> dict:
    from app.services import arbitration
    return {
        "id": d.id, "label": d.label, "definition_text": d.definition_text,
        "scope": d.scope, "space_id": d.space_id, "status": d.status,
        "is_reference": d.is_reference, "definition_version": d.definition_version,
        "impact_count": d.impact_count, "entity_label": d.entity_label,
        "owner_ref": d.owner_ref, **arbitration.freshness(db, d),
    }


@concepts_router.get("/{concept_id}")
def concept_detail(
    concept_id: int,
    space_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    from app.services import arbitration
    c = _owned_concept(db, concept_id, tenant)
    defs = arbitration.definitions_of(db, concept_id, space_id=space_id)
    return {
        **_concept_overview(db, c, space_id),
        "ambiguous": arbitration.is_ambiguous(db, concept_id, space_id=space_id),
        "definitions": [_definition_dict(db, d) for d in defs],
    }


@concepts_router.get("/{concept_id}/definitions")
def concept_definitions(
    concept_id: int,
    space_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[dict]:
    from app.services import arbitration
    _owned_concept(db, concept_id, tenant)
    return [_definition_dict(db, d) for d in arbitration.definitions_of(db, concept_id, space_id=space_id)]


@concepts_router.get("/{concept_id}/arbitration-preview")
def concept_arbitration_preview(
    concept_id: int,
    definition_id: int = Query(...),
    space_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Impact AVANT décision (rules 2 & 6) : options + population ET FRAÎCHEUR de
    chaque définition, effets de propagation, future version. Aucun effet de bord."""
    from app.services import arbitration
    _owned_concept(db, concept_id, tenant)
    return arbitration.arbitration_preview(db, concept_id, definition_id, space_id=space_id)


@concepts_router.post("/{concept_id}/definitions/{definition_id}/recompute",
                      dependencies=[Depends(require_analyst)])
def concept_recompute_impact(
    concept_id: int, definition_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Recalcule l'impact d'une définition sur ses sources et rafraîchit la
    fraîcheur (lève l'obsolescence). Le comptage réel court sur la source si elle
    est joignable ; sinon seule la fraîcheur est mise à jour."""
    from app.services import arbitration
    _owned_concept(db, concept_id, tenant)
    d = db.get(ConceptDefinition, definition_id)
    if d is None or d.concept_id != concept_id:
        raise HTTPException(status_code=404, detail="Définition introuvable.")
    adapter = conn_id = None
    for cid in (d.source_ids or []):
        c = db.get(Connection, cid)
        if c is not None and c.tenant_id == tenant.id:
            try:
                from app.services.connections import get_source_adapter
                adapter, conn_id = get_source_adapter(c), cid
                break
            except Exception:
                adapter = conn_id = None
    arbitration.recompute_impact(db, d, adapter=adapter, connection_id=conn_id)
    db.commit()
    return _definition_dict(db, d)


@concepts_router.post("/{concept_id}/arbitrate", dependencies=[Depends(require_analyst)])
def concept_arbitrate(
    concept_id: int,
    definition_id: int = Query(...),
    space_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Arbitrage TRANSACTIONNEL (rule 3) : référence + archivage + version + audit
    + propagation E1 en une seule opération. Contrôle de fraîcheur final : refuse
    d'arbitrer sur un impact obsolète (409). Échec ⇒ rollback total."""
    from app.services import arbitration
    _owned_concept(db, concept_id, tenant)
    try:
        result = arbitration.arbitrate(db, concept_id, definition_id,
                                       actor=tenant.name, space_id=space_id)
        db.commit()
    except arbitration.StaleImpactError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"version": result["version"], "propagation": result["propagation"],
            **concept_detail(concept_id, space_id, db, tenant)}
