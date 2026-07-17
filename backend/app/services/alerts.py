"""Alertes simples (V0.4).

Une alerte surveille une mesure scalaire (définition métier ou expression) et
se déclenche selon une condition simple. L'évaluation réutilise les garde-fous
d'exécution (read-only, EXPLAIN, timeout) : aucune requête n'échappe au cadre
de sécurité.

Conditions :
- gt / lt      : la valeur dépasse / passe sous le seuil ;
- pct_drop     : chute de plus de N% par rapport à la mesure précédente ;
- pct_change   : variation absolue de plus de N% par rapport à la précédente.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.alert import Alert, AlertEvent
from app.models.connection import Connection
from app.models.definitions import BusinessDefinition
from app.models.tenant import TenantSettings
from app.services.connections import get_source_adapter

log = get_logger("noreon.alerts")


def _alert_sql(db: Session, alert: Alert) -> str:
    """Construit la requête scalaire de la mesure surveillée."""
    schema = alert.schema_name
    table = alert.table_name
    expression = alert.expression
    filter_sql = alert.filter_sql

    if alert.definition_id is not None:
        d = db.get(BusinessDefinition, alert.definition_id)
        if d is not None and d.kind == "measure":
            schema, table = d.schema_name, d.table_name
            expression = d.expression
            filter_sql = d.filter_sql or filter_sql

    if not table or not expression:
        raise ValueError("Alerte mal configurée : table et expression requises.")

    where = f" WHERE {filter_sql}" if filter_sql else ""
    return f"SELECT {expression} AS value FROM {schema}.{table}{where}"


def _evaluate_condition(alert: Alert, value: float) -> tuple[str, str]:
    """Retourne (status, message) selon la condition et la valeur précédente."""
    prev = alert.last_value
    if alert.comparison == "gt":
        if value > alert.threshold:
            return "triggered", f"Valeur {value:,.2f} au-dessus du seuil {alert.threshold:,.2f}."
        return "ok", f"Valeur {value:,.2f} sous le seuil {alert.threshold:,.2f}."
    if alert.comparison == "lt":
        if value < alert.threshold:
            return "triggered", f"Valeur {value:,.2f} sous le seuil {alert.threshold:,.2f}."
        return "ok", f"Valeur {value:,.2f} au-dessus du seuil {alert.threshold:,.2f}."

    # Conditions relatives : nécessitent une mesure précédente.
    if prev is None:
        return "ok", f"Première mesure ({value:,.2f}) — référence enregistrée."
    if prev == 0:
        return "ok", f"Valeur précédente nulle, variation non calculable (valeur {value:,.2f})."
    change = (value - prev) / abs(prev) * 100
    if alert.comparison == "pct_drop":
        if -change > alert.threshold:
            return "triggered", f"Chute de {-change:.1f}% ({prev:,.2f} → {value:,.2f})."
        return "ok", f"Variation {change:+.1f}% ({prev:,.2f} → {value:,.2f})."
    if alert.comparison == "pct_change":
        if abs(change) > alert.threshold:
            return "triggered", f"Variation {change:+.1f}% ({prev:,.2f} → {value:,.2f})."
        return "ok", f"Variation {change:+.1f}% ({prev:,.2f} → {value:,.2f})."
    return "ok", "Condition inconnue."


def evaluate(db: Session, alert: Alert, conn: Connection) -> AlertEvent:
    """Évalue une alerte, met à jour son état et enregistre un événement."""
    settings = db.get(TenantSettings, conn.tenant_id)
    timeout = settings.sql_timeout_seconds if settings else 60
    max_cost = settings.sql_max_cost if settings else 1_000_000.0

    try:
        sql = _alert_sql(db, alert)
        adapter = get_source_adapter(conn)
        result = adapter.run_query(
            sql, connection_id=conn.id,
            row_limit=10, timeout_seconds=timeout, max_cost=max_cost, max_concurrent=1,
        )
        raw = result.rows[0][0] if result.rows and result.rows[0] else None
        value = float(raw) if raw is not None else None
        if value is None:
            status, message = "error", "La mesure n'a retourné aucune valeur."
        else:
            status, message = _evaluate_condition(alert, value)
            alert.previous_value = alert.last_value
            alert.last_value = value
    except Exception as exc:  # noqa: BLE001
        status, message, value = "error", str(exc), None
        log.warning("Alerte %s en erreur : %s", alert.id, exc)

    alert.last_status = status
    alert.last_message = message
    alert.last_checked_at = datetime.now(timezone.utc)

    event = AlertEvent(alert_id=alert.id, value=value, status=status, message=message)
    db.add(event)
    db.flush()
    return event


def evaluate_all(db: Session, conn: Connection) -> list[AlertEvent]:
    from sqlalchemy import select

    alerts = db.execute(
        select(Alert).where(Alert.connection_id == conn.id)
    ).scalars().all()
    return [evaluate(db, a, conn) for a in alerts]
