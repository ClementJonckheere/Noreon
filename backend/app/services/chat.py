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
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm import get_provider_for_tenant
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.query_log import QueryLog
from app.models.tenant import TenantSettings
from app.services import confidence as confidence_svc
from app.services import telemetry
from app.services.connections import get_source_adapter
from app.services.executor import CostThresholdExceeded
from app.services.schema_context import build_context, current_snapshot
from app.services.sql_guard import SQLGuardError

log = get_logger("noreon.chat")


@dataclass
class ChatResponse:
    status: str  # answered | clarification | unanswerable | blocked | error | no_schema
    question: str
    message: str = ""
    sql: str | None = None
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    rationale: str = ""
    explanations: list[str] = field(default_factory=list)
    # « Preuve » quantifiée du choix de table (couverture colonnes, score qualité,
    # concept métier validé) — transforme la justification en démonstration.
    proof: dict | None = None
    # Validation Engine (« relecture ») : contrôles, hypothèses explicites,
    # score de fiabilité du rapport, verdict « je ne peux pas conclure ».
    validation: dict | None = None
    # Arbitrage de mesure (montants contradictoires) : recommandation + pourquoi.
    measure_options: dict | None = None
    # Sources citées (comme un article) : tables sur lesquelles s'appuie la réponse.
    sources: list[dict] = field(default_factory=list)
    # « What if ? » : projection d'un scénario (« et si le panier moyen +10% ? »).
    simulation: dict | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    duration_ms: int | None = None
    estimated_cost: float | None = None
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    analysis: dict | None = None
    deep: dict | None = None
    investigation: dict | None = None
    confidence: dict | None = None
    table_quality: dict = field(default_factory=dict)
    chart: dict | None = None
    privacy: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _pii_columns(db: Session, connection_id: int, tables_used: list[str]) -> dict[str, str]:
    """Colonnes PII des tables utilisées (détectées par le profilage) → type."""
    names = [t.split(".")[-1] for t in tables_used]
    if not names:
        return {}
    profiles = db.execute(
        select(ColumnProfile).where(
            ColumnProfile.connection_id == connection_id,
            ColumnProfile.table_name.in_(names),
            ColumnProfile.pii_type.is_not(None),
        )
    ).scalars().all()
    return {p.column_name: p.pii_type for p in profiles}


def answer_question(
    db: Session,
    conn: Connection,
    question: str,
    *,
    user_ref: str = "system",
    run_analysis: bool = True,
    deep_analysis: bool = True,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
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

    # Gouvernance par espace : les tables/colonnes masquées n'entrent jamais
    # dans le contexte fourni au moteur SQL (il ne peut pas les proposer).
    context = build_context(db, snapshot, hidden_tables=hidden_tables, hidden_columns=hidden_columns)

    # Dictionnaire métier validé (Module 5) : la mémoire entreprise enrichit
    # le contexte du moteur SQL (LLM cloud comme heuristique hors-ligne).
    from app.services.semantic import validated_concepts_context

    concepts_text, _ = validated_concepts_context(db, conn.id)
    if concepts_text:
        context = context + "\n" + concepts_text

    # Définitions métier réutilisables (V0.4) : mesures et segments nommés.
    from app.services.definitions import definitions_context

    defs_text = definitions_context(db, conn.tenant_id)
    if defs_text:
        context = context + "\n" + defs_text

    # Contexte d'entreprise (D) : les conventions d'analyse (TTC, mensuel,
    # « France uniquement »…) sont connues du moteur et jamais redemandées.
    from app.services import company_context as company_ctx

    company = company_ctx.get_context(tenant_settings) if tenant_settings else company_ctx.get_context(None)
    company_block = company_ctx.context_block(company)
    if company_block:
        context = context + "\n" + company_block
    company_hypotheses = company_ctx.as_hypotheses(company)

    adapter = get_source_adapter(conn)

    # Réglages garde-fous (tenant > défauts globaux) — utiles à l'agent aussi.
    row_limit = tenant_settings.sql_row_limit if tenant_settings else 10_000
    timeout = tenant_settings.sql_timeout_seconds if tenant_settings else 60
    max_cost = tenant_settings.sql_max_cost if tenant_settings else 1_000_000.0
    max_conc = tenant_settings.sql_max_concurrent_per_connection if tenant_settings else 1
    guard_args = {"row_limit": row_limit, "timeout_seconds": timeout,
                  "max_cost": max_cost, "max_concurrent": max_conc}

    # 0bis) « What if ? » : question de scénario (« et si le panier moyen
    # augmentait de 10% ? ») → on projette au lieu d'analyser l'existant.
    if run_analysis:
        from app.services import simulation as sim_svc

        if sim_svc.detect(question):
            try:
                sim = sim_svc.run_simulation(
                    db, conn, adapter, question, guard_args=guard_args,
                    hidden_tables=hidden_tables, hidden_columns=hidden_columns,
                )
            except Exception as exc:  # noqa: BLE001 - best-effort
                log.warning("Simulation indisponible : %s", exc)
                sim = None
            if sim is not None:
                telemetry.record_usage("whatif_run")
                _log_query(db, conn, question, "-- simulation what-if --", None,
                           status="ok", row_count=len(sim.breakdown))
                cols = ["segment", "gain"]
                rows = [[b["segment"], b["gain"]] for b in sim.breakdown]
                from app.services.charting import suggest_chart

                chart = suggest_chart(cols, rows) if rows else None
                return ChatResponse(
                    status="answered", question=question, message=sim.narrative,
                    rationale="Projection de scénario (simulation hors-ligne, hypothèses affichées).",
                    tables_used=[sim.lever], simulation=sim.as_dict(),
                    columns=cols, rows=rows, row_count=len(rows),
                    chart=chart.as_dict() if chart else None,
                )

    # 0) Agent d'investigation : pour une question ANALYTIQUE ouverte (« pourquoi
    # les ventes baissent ? »), on planifie et on enchaîne des sous-questions au
    # lieu d'un SQL unique. Repli silencieux sur le pipeline normal si le sujet
    # ne s'y prête pas.
    if deep_analysis and run_analysis:
        from app.services import agent as agent_svc

        if agent_svc.should_investigate(question):
            try:
                inv = agent_svc.run_investigation(
                    db, conn, adapter, question, guard_args=guard_args,
                    hidden_tables=hidden_tables, hidden_columns=hidden_columns,
                )
            except Exception as exc:  # noqa: BLE001 - best-effort
                log.warning("Agent d'investigation indisponible : %s", exc)
                inv = None
            if inv is not None:
                from app.services.charting import suggest_chart

                chart = suggest_chart(inv.trend_columns, inv.trend_rows) if inv.trend_rows else None
                conf = confidence_svc.compute(
                    db, connection_id=conn.id, tables_used=[inv.subject],
                    assumptions=[], sampled=_any_sampled(db, conn.id, [inv.subject]),
                    truncated=False, row_count=len(inv.trend_rows),
                )
                _log_query(db, conn, question, "-- investigation multi-étapes --", None,
                           status="ok", row_count=len(inv.steps), confidence=conf.as_dict())
                # Relecture : sur une investigation causale, le moteur peut
                # conclure « je ne peux pas conclure » s'il n'a pas isolé de driver.
                from app.services import validation as validation_svc

                inv_validation = validation_svc.validate(
                    db, conn, question=question, sql="",
                    tables_used=[inv.subject], columns_used=inv.trend_columns,
                    row_count=len(inv.trend_rows), truncated=False, assumptions=[],
                    confidence_score=conf.score, has_drivers=bool(inv.key_drivers),
                    causal_hint=True,
                ).as_dict()
                return ChatResponse(
                    status="answered", question=question,
                    message=agent_svc.summary_message(inv),
                    rationale="Investigation multi-étapes (planification → sous-questions → synthèse).",
                    tables_used=[inv.subject],
                    columns=inv.trend_columns, rows=inv.trend_rows, row_count=len(inv.trend_rows),
                    investigation=inv.as_dict(), confidence=conf.as_dict(),
                    validation=inv_validation,
                    sources=_sources([inv.subject], inv.trend_columns, {}),
                    chart=chart.as_dict() if chart else None,
                )

    # 1) Génération SQL via la couche LLM, dans le dialecte du moteur source.
    _t_llm = perf_counter()
    gen = provider.generate_sql(question, context, dialect=adapter.dialect)
    telemetry.record_llm((perf_counter() - _t_llm) * 1000,
                         tokens=getattr(gen, "tokens", 0) or 0)

    if gen.unanswerable:
        # Refus honnête : l'information demandée est absente des données. On
        # préfère le dire plutôt que de deviner (indicateur CDC « impossible »).
        _log_query(db, conn, question, "", gen, status="unanswerable",
                   block_reason=gen.unanswerable)
        return ChatResponse(
            status="unanswerable", question=question,
            message=gen.unanswerable, rationale=gen.rationale,
        )

    if gen.clarification_needed:
        # « Il ne devine jamais silencieusement » — on remonte la question.
        # Journalisé pour mesurer le taux de clarifications (observabilité).
        _log_query(db, conn, question, "", gen, status="clarification",
                   block_reason=gen.clarification_needed)
        return ChatResponse(
            status="clarification", question=question,
            message=gen.clarification_needed, rationale=gen.rationale,
        )

    if not gen.sql:
        return ChatResponse(
            status="error", question=question,
            message="Le moteur n'a pas pu produire de requête pour cette question.",
        )

    # Gouvernance (défense en profondeur) : si malgré le filtrage du contexte la
    # requête référence une table masquée pour l'espace, on bloque explicitement.
    if hidden_tables:
        from app.services.sql_guard import referenced_tables

        refs = referenced_tables(gen.sql, adapter.dialect)
        blocked = refs & {t.lower() for t in hidden_tables}
        if blocked:
            return ChatResponse(
                status="blocked", question=question, sql=gen.sql,
                message="Accès refusé par la gouvernance de l'espace : la ou les tables "
                        f"{', '.join(sorted(blocked))} ne sont pas autorisées ici.",
            )

    # 2) Garde-fous + exécution read-only (réglages déjà lus plus haut).
    try:
        result = adapter.run_query(
            gen.sql, connection_id=conn.id,
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

    # 3) Privacy Engine (§5.1) : pseudonymisation des PII avant analyse LLM,
    # puis ré-identification LOCALE dans le rapport produit.
    from app.services import privacy as privacy_svc

    pii_cols = _pii_columns(db, conn.id, gen.tables_used or result.columns)
    protection = privacy_svc.protect(result.columns, result.rows, pii_cols)

    analysis = None
    if run_analysis:
        try:
            a = provider.analyze_results(
                question, result.guarded_sql, result.columns, protection.rows
            )
            analysis = privacy_svc.reidentify_analysis(asdict(a), protection.token_map)
        except Exception as exc:  # noqa: BLE001 - repli sur tableau brut (agent Reporting)
            log.warning("Analyse LLM indisponible, repli tableau brut : %s", exc)

    # 3bis) Analyse approfondie (valeur métier) : au-delà de la sortie brute,
    # on croise les dimensions autour du sujet via des requêtes de suivi en
    # lecture seule (segmentation, drivers, croisements). Jamais bloquant :
    # tout échec retombe silencieusement sur le rapport chiffré standard.
    deep = None
    if deep_analysis and run_analysis:
        from app.services import deep_analysis as deep_svc

        guard_args = {
            "row_limit": row_limit, "timeout_seconds": timeout,
            "max_cost": max_cost, "max_concurrent": max_conc,
        }
        try:
            report = deep_svc.run_deep_analysis(
                db, conn, adapter, question,
                tables_used=gen.tables_used, guard_args=guard_args,
            )
            deep = report.as_dict() if report is not None else None
        except Exception as exc:  # noqa: BLE001 - analyse approfondie best-effort
            log.warning("Analyse approfondie indisponible : %s", exc)

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

    # Suggestion de graphique selon la nature des données (Module 9),
    # en respectant la préférence de type par défaut du tenant (V0.4).
    from app.services.charting import suggest_chart

    suggestion = suggest_chart(result.columns, result.rows)
    prefs = getattr(tenant_settings, "preferences", None) or {}
    preferred = prefs.get("preferred_chart_type") if isinstance(prefs, dict) else None
    if preferred and suggestion.type != "table" and preferred != suggestion.type:
        if preferred not in suggestion.alternatives:
            suggestion.alternatives = [suggestion.type, *suggestion.alternatives]
        suggestion.type = preferred
        suggestion.reason = f"Type imposé par la préférence de l'entreprise ({preferred})."
    chart = suggestion.as_dict()

    # Score qualité des tables utilisées (base d'arbitrage entre sources).
    from app.services.quality import table_scores_map

    tscores = table_scores_map(db, conn.id)
    table_quality = {
        t: round(tscores[t.split(".")[-1]] * 100)
        for t in gen.tables_used
        if t.split(".")[-1] in tscores
    }

    # Explicabilité « preuve » : pourquoi cette table, ces colonnes, cette
    # jointure, ce graphique — chaque choix est justifié (retour produit).
    explanations = _explanations(db, snapshot, gen, result.guarded_sql, chart)
    proof = _table_proof(db, conn, snapshot, gen, tscores)

    # Validation Engine (« relecture ») : le moteur vérifie sa propre analyse
    # avant de la montrer (mesure, dates, NULL, duplication, volume) et en
    # calcule la fiabilité + les hypothèses retenues.
    from app.services import validation as validation_svc

    has_drivers = bool(deep and deep.get("drivers"))
    validation = validation_svc.validate(
        db, conn, question=question, sql=result.guarded_sql,
        tables_used=gen.tables_used, columns_used=gen.columns_used or result.columns,
        row_count=result.row_count, truncated=result.truncated,
        assumptions=gen.assumptions, confidence_score=conf.score,
        has_drivers=has_drivers, context_hypotheses=company_hypotheses,
    ).as_dict()

    return ChatResponse(
        status="answered", question=question, sql=result.guarded_sql,
        tables_used=gen.tables_used, columns_used=gen.columns_used or result.columns,
        assumptions=gen.assumptions, rationale=gen.rationale, explanations=explanations,
        proof=proof, validation=validation, measure_options=gen.measure_options,
        sources=_sources(gen.tables_used, gen.columns_used, tscores),
        columns=result.columns, rows=result.rows, row_count=result.row_count,
        duration_ms=result.duration_ms, estimated_cost=result.estimated_cost,
        truncated=result.truncated, warnings=result.warnings,
        analysis=analysis, deep=deep, confidence=conf.as_dict(), table_quality=table_quality,
        chart=chart, privacy=protection.audit,
    )


def _evidence_level(*, quality_pct: int | None = None, concept: bool = False,
                    inferred: bool = False, assumptions: int = 0) -> str:
    """Niveau de preuve — toutes les preuves n'ont pas la même valeur.

    🟢 forte : FK déclarée / concept validé / qualité > 98 %.
    🟡 moyenne : relation inférée / concept suggéré / quelques NULL.
    🔴 faible : heuristique seule / peu de données / hypothèses nombreuses.
    """
    if assumptions >= 3 or (quality_pct is not None and quality_pct < 70):
        return "weak"
    if (quality_pct is not None and quality_pct >= 98) or concept:
        if not inferred and assumptions == 0:
            return "strong"
    if inferred or assumptions >= 1 or (quality_pct is not None and quality_pct < 90):
        return "medium"
    return "strong" if quality_pct is not None else "medium"


def _sources(tables_used: list[str], columns_used: list[str], tscores: dict) -> list[dict]:
    """Cite les sources de la réponse (comme un article) : table principale puis
    tables jointes, avec leur score qualité et leur niveau de preuve."""
    out: list[dict] = []
    seen: set[str] = set()
    for i, t in enumerate(tables_used or []):
        name = t.split(".")[-1]
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        q = tscores.get(name.lower())
        qpct = round(q * 100) if q is not None else None
        out.append({
            "table": name,
            "role": "principale" if i == 0 else "jointe",
            "quality_pct": qpct,
            "level": _evidence_level(quality_pct=qpct),
        })
    return out


def _table_proof(db: Session, conn: Connection, snapshot, gen, tscores: dict) -> dict | None:
    """Transforme « pourquoi cette table ? » en PREUVE chiffrée et vérifiable :

        - couverture : X% des colonnes nécessaires sont présentes dans la table ;
        - qualité    : score qualité auditable de la table ;
        - concept    : concept métier VALIDÉ (boucle humaine) rattaché à la table.
    """
    if snapshot is None or not gen.tables_used:
        return None
    from app.models.schema_catalog import DbColumn, DbTable
    from app.models.semantic import BusinessConcept, ConceptMapping

    table = gen.tables_used[0].split(".")[-1]

    # Colonnes réelles du schéma (pour distinguer les vraies références des alias
    # calculés comme « periode » ou « total »).
    rows = db.execute(
        select(DbTable.table_name, DbColumn.name)
        .join(DbColumn, DbColumn.table_id == DbTable.id)
        .where(DbTable.snapshot_id == snapshot.id)
    ).all()
    all_cols = {c.lower() for _, c in rows}
    table_cols = {c.lower() for t, c in rows if t.lower() == table.lower()}

    used = [c.lower() for c in (gen.columns_used or [])]
    needed = [c for c in used if c in all_cols]          # vraies colonnes citées
    present = [c for c in needed if c in table_cols]
    coverage = round(len(present) / len(needed) * 100) if needed else 100
    quality_pct = round(tscores.get(table.lower(), 0) * 100) if tscores.get(table.lower()) else None

    # Concept métier VALIDÉ rattaché à cette table (mémoire entreprise).
    concept = db.execute(
        select(BusinessConcept.name)
        .join(ConceptMapping, ConceptMapping.concept_id == BusinessConcept.id)
        .where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.table_name == table,
            ConceptMapping.status.in_(("validated", "corrected")),
        )
        .limit(1)
    ).scalar_one_or_none()

    steps = [f"{coverage}% des colonnes nécessaires présentes"
             + (f" ({len(present)}/{len(needed)})" if needed else "")]
    if quality_pct is not None:
        steps.append(f"score qualité {quality_pct}%")
    if concept:
        steps.append(f"concept validé : {concept}")
    return {
        "table": table,
        "coverage_pct": coverage,
        "columns_needed": len(needed),
        "columns_present": len(present),
        "quality_pct": quality_pct,
        "concept": concept,
        "level": _evidence_level(quality_pct=quality_pct, concept=bool(concept),
                                 assumptions=len(gen.assumptions or [])),
        "steps": steps,
    }


def _explanations(db: Session, snapshot, gen, guarded_sql: str, chart: dict | None) -> list[str]:
    """Compose une justification lisible de chaque décision de l'analyse."""
    from app.models.schema_catalog import DbRelation

    out: list[str] = []
    if gen.rationale:
        out.append(f"Table : {gen.rationale}")
    if gen.columns_used:
        out.append(f"Colonnes : {', '.join(gen.columns_used)} — retenues d'après la question.")

    # Jointure : si le SQL en contient une, on nomme la relation mobilisée.
    if snapshot is not None and " join " in f" {guarded_sql.lower()} ":
        used = {t.split('.')[-1].lower() for t in (gen.tables_used or [])}
        rels = db.execute(
            select(DbRelation).where(
                DbRelation.snapshot_id == snapshot.id, DbRelation.status != "rejected"
            )
        ).scalars().all()
        for r in rels:
            if r.from_table.lower() in used and r.to_table.lower() in used:
                tag = {"declared": "FK déclarée", "inferred": "FK inférée",
                       "validated": "FK validée"}.get(r.kind, r.kind)
                out.append(
                    f"Jointure : {r.from_table}.{r.from_column} → {r.to_table}.{r.to_column} "
                    f"({tag}) — c'est la relation qui relie ces tables."
                )
                break

    if chart:
        if chart.get("type") and chart["type"] != "table":
            out.append(f"Graphique « {chart['type']} » : {chart.get('reason', '')}".strip())
        elif chart.get("reason"):
            out.append(f"Affichage en tableau : {chart['reason']}")
    return out


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
