"""Pipeline de chat NL→SQL (Module 7) avec transparence et garde-fous.

Étapes (cf. cahier des charges) :
  interprétation → désambiguïsation → sélection des tables (guidée par le
  catalogue + relations) → construction SQL → validation (garde-fous) →
  exécution read-only → anonymisation PII → interprétation → réponse.

Chaque réponse expose SON RAISONNEMENT : SQL généré, tables/colonnes/filtres
utilisés, temps d'exécution, indice de confiance calibré (Module 10).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm import get_provider_for_tenant
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.query_log import QueryLog
from app.models.tenant import TenantSettings
from app.services import confidence as confidence_svc
from app.services.connections import source_config
from app.services.executor import CostThresholdExceeded, run_query
from app.services.schema_context import build_context, current_snapshot
from app.services.sql_guard import SQLGuardError

log = get_logger("noreon.chat")


@dataclass
class ChatResponse:
    status: str  # answered | clarification | blocked | error | no_schema
    question: str
    message: str = ""
    sql: str | None = None
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    rationale: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    duration_ms: int | None = None
    estimated_cost: float | None = None
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    analysis: dict | None = None
    confidence: dict | None = None
    table_quality: dict = field(default_factory=dict)
    chart: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _pii_columns(db: Session, connection_id: int, tables_used: list[str]) -> set[str]:
    names = [t.split(".")[-1] for t in tables_used]
    if not names:
        return set()
    profiles = db.execute(
        select(ColumnProfile).where(
            ColumnProfile.connection_id == connection_id,
            ColumnProfile.table_name.in_(names),
            ColumnProfile.pii_type.is_not(None),
        )
    ).scalars().all()
    return {p.column_name for p in profiles}


def _anonymize(columns: list[str], rows: list[list], pii_cols: set[str]) -> list[list]:
    """Masque les colonnes PII avant tout envoi au LLM (contrat Privacy Engine).

    En V0.1 on pseudonymise par masquage ; l'anonymisation avancée
    (agrégation, généralisation) sera formalisée par le Privacy Engine en V0.3.
    """
    if not pii_cols:
        return rows
    mask_idx = {i for i, c in enumerate(columns) if c in pii_cols}
    if not mask_idx:
        return rows
    masked: list[list] = []
    for r in rows:
        masked.append([("***" if i in mask_idx else v) for i, v in enumerate(r)])
    return masked


def answer_question(
    db: Session,
    conn: Connection,
    question: str,
    *,
    user_ref: str = "system",
    run_analysis: bool = True,
) -> ChatResponse:
    tenant_settings = db.get(TenantSettings, conn.tenant_id)
    provider = get_provider_for_tenant(tenant_settings)

    # Garde-fou amont : la connexion doit être read-only confirmée.
    if conn.is_read_only is False:
        return ChatResponse(
            status="blocked", question=question,
            message="Connexion bloquée : le compte source n'est pas en lecture seule. "
                    "Corrigez les droits avant toute analyse.",
        )

    snapshot = current_snapshot(db, conn.id)
    if snapshot is None:
        return ChatResponse(
            status="no_schema", question=question,
            message="Aucun schéma scanné pour cette connexion. Lancez d'abord un scan.",
        )

    context = build_context(db, snapshot)

    # Dictionnaire métier validé (Module 5) : la mémoire entreprise enrichit
    # le contexte du moteur SQL (LLM cloud comme heuristique hors-ligne).
    from app.services.semantic import validated_concepts_context

    concepts_text, _ = validated_concepts_context(db, conn.id)
    if concepts_text:
        context = context + "\n" + concepts_text

    # 1) Génération SQL via la couche LLM (dialecte postgres).
    gen = provider.generate_sql(question, context, dialect="postgres")

    if gen.clarification_needed:
        # « Il ne devine jamais silencieusement » — on remonte la question.
        return ChatResponse(
            status="clarification", question=question,
            message=gen.clarification_needed, rationale=gen.rationale,
        )

    if not gen.sql:
        return ChatResponse(
            status="error", question=question,
            message="Le moteur n'a pas pu produire de requête pour cette question.",
        )

    # Réglages garde-fous (tenant > défauts globaux).
    row_limit = tenant_settings.sql_row_limit if tenant_settings else 10_000
    timeout = tenant_settings.sql_timeout_seconds if tenant_settings else 60
    max_cost = tenant_settings.sql_max_cost if tenant_settings else 1_000_000.0
    max_conc = tenant_settings.sql_max_concurrent_per_connection if tenant_settings else 1

    cfg = source_config(conn)

    # 2) Garde-fous + exécution read-only.
    try:
        result = run_query(
            cfg, gen.sql, connection_id=conn.id,
            row_limit=row_limit, timeout_seconds=timeout,
            max_cost=max_cost, max_concurrent=max_conc,
        )
    except CostThresholdExceeded as exc:
        _log_query(db, conn, question, gen.sql, gen, status="blocked",
                   block_reason=str(exc), estimated_cost=exc.cost)
        return ChatResponse(
            status="blocked", question=question, sql=gen.sql,
            tables_used=gen.tables_used, message=str(exc), estimated_cost=exc.cost,
        )
    except SQLGuardError as exc:
        _log_query(db, conn, question, gen.sql, gen, status="blocked", block_reason=str(exc))
        return ChatResponse(
            status="blocked", question=question, sql=gen.sql,
            tables_used=gen.tables_used, message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - erreur d'exécution source
        _log_query(db, conn, question, gen.sql, gen, status="error", block_reason=str(exc))
        return ChatResponse(
            status="error", question=question, sql=gen.sql,
            message=f"Erreur d'exécution : {exc}",
        )

    # 3) Anonymisation PII avant analyse LLM.
    pii_cols = _pii_columns(db, conn.id, gen.tables_used or result.columns)
    safe_rows = _anonymize(result.columns, result.rows, pii_cols)

    analysis = None
    if run_analysis:
        try:
            a = provider.analyze_results(question, result.guarded_sql, result.columns, safe_rows)
            analysis = asdict(a)
        except Exception as exc:  # noqa: BLE001 - repli sur tableau brut (agent Reporting)
            log.warning("Analyse LLM indisponible, repli tableau brut : %s", exc)

    # 4) Indice de confiance calibré.
    sampled = _any_sampled(db, conn.id, gen.tables_used)
    conf = confidence_svc.compute(
        db, connection_id=conn.id, tables_used=gen.tables_used,
        assumptions=gen.assumptions, sampled=sampled,
        truncated=result.truncated, row_count=result.row_count,
    )

    # 5) Audit immuable.
    _log_query(
        db, conn, question, result.guarded_sql, gen, status="ok",
        estimated_cost=result.estimated_cost, row_count=result.row_count,
        duration_ms=result.duration_ms, truncated=result.truncated,
        confidence=conf.as_dict(),
    )

    # Suggestion de graphique selon la nature des données (Module 9).
    from app.services.charting import suggest_chart

    chart = suggest_chart(result.columns, result.rows).as_dict()

    # Score qualité des tables utilisées (base d'arbitrage entre sources).
    from app.services.quality import table_scores_map

    tscores = table_scores_map(db, conn.id)
    table_quality = {
        t: round(tscores[t.split(".")[-1]] * 100)
        for t in gen.tables_used
        if t.split(".")[-1] in tscores
    }

    return ChatResponse(
        status="answered", question=question, sql=result.guarded_sql,
        tables_used=gen.tables_used, columns_used=gen.columns_used or result.columns,
        assumptions=gen.assumptions, rationale=gen.rationale,
        columns=result.columns, rows=result.rows, row_count=result.row_count,
        duration_ms=result.duration_ms, estimated_cost=result.estimated_cost,
        truncated=result.truncated, warnings=result.warnings,
        analysis=analysis, confidence=conf.as_dict(), table_quality=table_quality,
        chart=chart,
    )


def _any_sampled(db: Session, connection_id: int, tables_used: list[str]) -> bool:
    names = [t.split(".")[-1] for t in tables_used]
    if not names:
        return False
    rows = db.execute(
        select(ColumnProfile.sampled).where(
            ColumnProfile.connection_id == connection_id,
            ColumnProfile.table_name.in_(names),
        )
    ).scalars().all()
    return any(rows)


def _log_query(
    db: Session, conn: Connection, question: str, sql: str, gen,
    *, status: str, block_reason: str | None = None,
    estimated_cost: float | None = None, row_count: int | None = None,
    duration_ms: int | None = None, truncated: bool = False,
    confidence: dict | None = None,
) -> None:
    db.add(QueryLog(
        tenant_id=conn.tenant_id, connection_id=conn.id, user_ref="system",
        question=question, sql=sql,
        tables_used=getattr(gen, "tables_used", []) or [],
        columns_used=getattr(gen, "columns_used", []) or [],
        filters=[], status=status, block_reason=block_reason,
        estimated_cost=estimated_cost, row_count=row_count,
        duration_ms=duration_ms, truncated=truncated,
        confidence=confidence or {},
    ))
    db.flush()
