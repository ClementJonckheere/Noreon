"""Couche d'abstraction des sources de données (V1.0).

Comme la couche LLM (§6), le code métier ne connaît qu'une interface —
`SourceAdapter` — et jamais les spécificités d'un SGBD. Chaque moteur
(PostgreSQL, MySQL, CSV/Excel) fournit son implémentation ; le scanner, le
profileur, le chat et les alertes fonctionnent à l'identique sur tous.

Principes préservés pour TOUTES les sources :
- lecture seule stricte ;
- garde-fous d'exécution (LIMIT automatique, coût, timeout, file par connexion) ;
- introspection + relations implicites ;
- profilage portable.
"""
from __future__ import annotations

import abc
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field

from app.services.sql_guard import GuardedSQL, SQLGuardError, guard


# ---------------------------------------------------------------------------
# Config & résultats partagés
# ---------------------------------------------------------------------------
@dataclass
class SourceConfig:
    engine: str  # postgresql | mysql | csv | excel | sqlite
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str = ""
    password: str = ""
    sslmode: str = "prefer"
    connect_timeout: int = 10
    options: dict = field(default_factory=dict)
    # Sources fichier : chemin local matérialisé (CSV/Excel → SQLite).
    file_path: str | None = None


@dataclass
class ColumnInfo:
    name: str
    ordinal: int
    data_type: str
    is_nullable: bool
    default: str | None
    is_pk: bool = False


@dataclass
class TableInfo:
    schema: str
    name: str
    table_type: str
    estimated_rows: int | None
    comment: str | None
    columns: list[ColumnInfo] = field(default_factory=list)


@dataclass
class RelationInfo:
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    kind: str  # declared | inferred
    confidence: float
    details: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    tables: list[TableInfo]
    relations: list[RelationInfo]

    def signature(self) -> str:
        payload = {
            "tables": [
                {
                    "s": t.schema, "n": t.name, "t": t.table_type,
                    "cols": [[c.name, c.data_type, c.is_nullable, c.is_pk] for c in t.columns],
                }
                for t in sorted(self.tables, key=lambda x: (x.schema, x.name))
            ],
            "rels": sorted(
                [[r.from_schema, r.from_table, r.from_column, r.to_schema, r.to_table, r.to_column, r.kind]
                 for r in self.relations]
            ),
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    duration_ms: int
    truncated: bool
    estimated_cost: float | None
    guarded_sql: str
    limit_applied: int | None
    warnings: list[str] = field(default_factory=list)


class CostThresholdExceeded(SQLGuardError):
    def __init__(self, cost: float, threshold: float) -> None:
        super().__init__(
            f"Requête bloquée : coût estimé {cost:,.0f} supérieur au seuil autorisé "
            f"{threshold:,.0f} (risque de produit cartésien ou de scan massif). "
            "Ajoutez des filtres ou réduisez la portée."
        )
        self.cost = cost
        self.threshold = threshold


# --- file d'exécution : un sémaphore borné par connexion source (in-process) ---
_locks_guard = threading.Lock()
_conn_semaphores: dict[int, threading.Semaphore] = {}


def _semaphore_for(connection_id: int, max_concurrent: int) -> threading.Semaphore:
    with _locks_guard:
        sem = _conn_semaphores.get(connection_id)
        if sem is None:
            sem = threading.Semaphore(max_concurrent)
            _conn_semaphores[connection_id] = sem
        return sem


# ---------------------------------------------------------------------------
# Détection de relations implicites (partagée par tous les adaptateurs)
# ---------------------------------------------------------------------------
_INTEGER_TYPES = {
    "integer", "bigint", "smallint", "int", "int2", "int4", "int8",
    "serial", "bigserial", "tinyint", "mediumint", "numeric",
}


def infer_relations(
    tables: list[TableInfo],
    declared_pairs: set[tuple],
) -> list[RelationInfo]:
    """Relations implicites via la convention `xxx_id` — indépendant du SGBD."""
    by_name: dict[str, tuple[TableInfo, str]] = {}
    for t in tables:
        pks = [c for c in t.columns if c.is_pk]
        if len(pks) == 1:
            by_name.setdefault(t.name.lower(), (t, pks[0].name))

    def candidates(base: str) -> list[str]:
        base = base.lower()
        return [base, base + "s", base + "es",
                (base[:-1] + "ies") if base.endswith("y") else base]

    inferred: list[RelationInfo] = []
    for t in tables:
        for col in t.columns:
            cname = col.name.lower()
            if not cname.endswith("_id") and not (cname.endswith("id") and len(cname) > 2):
                continue
            base = cname[:-3] if cname.endswith("_id") else cname[:-2]
            if not base or col.data_type.lower() not in _INTEGER_TYPES:
                continue
            if (t.schema, t.name, col.name) in declared_pairs:
                continue
            target = None
            for cand in candidates(base):
                if cand in by_name and by_name[cand][0].name.lower() != t.name.lower():
                    target = by_name[cand]
                    break
            if target is None:
                continue
            target_table, target_pk = target
            target_col = next((c for c in target_table.columns if c.name == target_pk), None)
            if target_col is None or target_col.data_type.lower() not in _INTEGER_TYPES:
                continue
            confidence = 0.8 if base == target_table.name.lower() else 0.65
            inferred.append(RelationInfo(
                from_schema=t.schema, from_table=t.name, from_column=col.name,
                to_schema=target_table.schema, to_table=target_table.name, to_column=target_pk,
                kind="inferred", confidence=confidence,
                details={"rule": "naming_convention_xxx_id"},
            ))
    return inferred


# ---------------------------------------------------------------------------
# Interface d'adaptateur
# ---------------------------------------------------------------------------
class SourceAdapter(abc.ABC):
    engine: str = "abstract"
    dialect: str = "postgres"  # dialecte sqlglot pour les garde-fous

    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    # --- connexion / conformité ---
    @abc.abstractmethod
    def test_connection(self) -> dict:
        """{ok, server_version, error}"""

    @abc.abstractmethod
    def check_read_only(self) -> dict:
        """{read_only, detail, error}"""

    # --- introspection ---
    @abc.abstractmethod
    def introspect(self) -> ScanResult:
        ...

    # --- primitives bas niveau pour le profileur portable ---
    @abc.abstractmethod
    def fetch(self, sql: str, params: tuple | None = None) -> tuple[list[str], list[list]]:
        """Exécute une requête de lecture et renvoie (colonnes, lignes)."""

    def quote_ident(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def qualified(self, schema: str, table: str) -> str:
        return f"{self.quote_ident(schema)}.{self.quote_ident(table)}"

    def length_of(self, ident_sql: str) -> str:
        """Expression SQL de la longueur textuelle d'une valeur (dialecte)."""
        return f"length(cast({ident_sql} as text))"

    def sample_source(self, schema: str, table: str, estimated_rows: int | None) -> tuple[str, bool]:
        """Renvoie (expression FROM à profiler, échantillonné?)."""
        from app.core.config import settings

        fq = self.qualified(schema, table)
        threshold = settings.profiling_sample_threshold
        if estimated_rows is not None and estimated_rows >= threshold:
            n = settings.profiling_sample_size
            return f"(SELECT * FROM {fq} ORDER BY random() LIMIT {n}) AS _noreon_s", True
        return fq, False

    def is_numeric_type(self, declared_type: str) -> bool:
        d = declared_type.lower()
        return any(k in d for k in (
            "int", "numeric", "decimal", "real", "double", "float", "money", "dec"
        )) and "point" not in d

    def is_sortable_type(self, declared_type: str) -> bool:
        return not any(u in declared_type.lower() for u in
                       ("json", "jsonb", "xml", "bytea", "blob", "array", "geometry"))

    # --- intégrité référentielle (Module 4/6) ---
    def compute_integrity(self, rel, timeout_ms: int) -> dict | None:
        """Taux d'orphelins + cardinalité réels (portable via LEFT JOIN)."""
        fq_from = self.qualified(rel.from_schema, rel.from_table)
        fq_to = self.qualified(rel.to_schema, rel.to_table)
        fcol = self.quote_ident(rel.from_column)
        tcol = self.quote_ident(rel.to_column)
        sql = (
            f"SELECT count(*) AS total, "
            f"sum(CASE WHEN t.{tcol} IS NULL THEN 1 ELSE 0 END) AS orphans, "
            f"count(DISTINCT f.{fcol}) AS distinct_from "
            f"FROM {fq_from} f LEFT JOIN {fq_to} t ON f.{fcol} = t.{tcol} "
            f"WHERE f.{fcol} IS NOT NULL"
        )
        try:
            _, rows = self.fetch(sql)
        except Exception:  # noqa: BLE001
            return None
        if not rows:
            return None
        total, orphans, distinct_from = (int(x or 0) for x in rows[0])
        ratio = 1.0 if total == 0 else 1 - orphans / total
        cardinality = "1-1" if total > 0 and distinct_from == total else "n-1"
        return {
            "ratio": ratio, "orphans": orphans, "total": total,
            "to_table": f"{rel.to_schema}.{rel.to_table}", "cardinality": cardinality,
        }

    # --- exécution avec garde-fous (commun à tous les moteurs) ---
    def _estimate_cost(self, sql: str, timeout_ms: int) -> float:
        """Coût estimé (0 si le moteur ne fournit pas d'EXPLAIN chiffré)."""
        return 0.0

    @abc.abstractmethod
    def _execute(self, sql: str, timeout_seconds: int) -> tuple[list[str], list[list]]:
        """Exécute la requête (déjà sécurisée) et renvoie (colonnes, lignes)."""

    def run_query(
        self,
        raw_sql: str,
        *,
        connection_id: int,
        row_limit: int = 10_000,
        timeout_seconds: int = 60,
        max_cost: float = 1_000_000.0,
        max_concurrent: int = 1,
        enforce_cost: bool = True,
    ) -> ExecutionResult:
        guarded: GuardedSQL = guard(raw_sql, row_limit=row_limit, dialect=self.dialect)
        warnings: list[str] = []

        cost = self._estimate_cost(guarded.sql, timeout_seconds * 1000)
        if enforce_cost and cost > max_cost:
            raise CostThresholdExceeded(cost, max_cost)
        if cost and cost > max_cost * 0.5:
            warnings.append(f"Coût estimé élevé ({cost:,.0f}).")

        sem = _semaphore_for(connection_id, max_concurrent)
        if not sem.acquire(timeout=timeout_seconds):
            raise SQLGuardError(
                "File d'exécution saturée pour cette connexion source (trop de requêtes simultanées)."
            )
        try:
            start = time.perf_counter()
            columns, fetched = self._execute(guarded.sql, timeout_seconds)
            duration_ms = int((time.perf_counter() - start) * 1000)
        finally:
            sem.release()

        rows = [list(r) for r in fetched]
        truncated = guarded.limit_applied is not None and len(rows) >= guarded.limit_applied
        if truncated:
            warnings.append(f"Résultats tronqués à {guarded.limit_applied} lignes (LIMIT automatique).")

        return ExecutionResult(
            columns=columns, rows=rows, row_count=len(rows), duration_ms=duration_ms,
            truncated=truncated, estimated_cost=cost, guarded_sql=guarded.sql,
            limit_applied=guarded.limit_applied, warnings=warnings,
        )
