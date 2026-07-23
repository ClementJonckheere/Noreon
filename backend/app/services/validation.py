"""Validation Engine — la « relecture » de Noreon.

Aujourd'hui le moteur raisonne, mais il fait confiance à son SQL. Ce composant
**vérifie systématiquement une analyse avant de la montrer**, comme un analyste
qui se relit :

    Résultat → Vérification :
      • ai-je utilisé la bonne mesure (CA TTC plutôt que HT) ?
      • les dates sont-elles cohérentes (pas de futur, peu de NULL) ?
      • y a-t-il beaucoup de valeurs manquantes ?
      • une jointure a-t-elle pu dupliquer des lignes ?
      • le nombre de lignes est-il plausible ?

Il produit trois choses, toutes auditables et calculées hors-ligne :
- des **contrôles** (pass / warn / fail, chacun avec son détail chiffré) ;
- les **hypothèses retenues**, rendues explicites (mesure, grain, périmètre) ;
- un **score de fiabilité du rapport** (pas seulement du SQL) + ses facteurs.

Il peut aussi conclure « **je ne peux pas conclure** » : distinct de « impossible
de répondre », c'est le cas où l'analyse tourne mais où les données ne
permettent pas d'établir un lien de causalité.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import ColumnProfile
from app.models.schema_catalog import DbRelation, SchemaSnapshot
from app.models.semantic import ConceptMapping

_CAUSAL = re.compile(r"\b(pourquoi|cause[rs]?|expliqu\w+|raison|due?\b|à cause|driver)", re.I)
_AGG = re.compile(r"\b(sum|avg|count|min|max)\s*\(", re.I)


@dataclass
class Check:
    key: str
    label: str
    status: str  # pass | warn | fail
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Validation:
    checks: list[Check] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    reliability_percent: int = 100
    reliability_stars: int = 5
    reliability_factors: list[dict] = field(default_factory=list)  # {label, status}
    verdict: str | None = None        # None | "cannot_conclude"
    verdict_note: str | None = None

    def as_dict(self) -> dict:
        return {
            "checks": [c.as_dict() for c in self.checks],
            "hypotheses": self.hypotheses,
            "reliability_percent": self.reliability_percent,
            "reliability_stars": self.reliability_stars,
            "reliability_factors": self.reliability_factors,
            "verdict": self.verdict,
            "verdict_note": self.verdict_note,
        }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def validate(
    db: Session, conn, *, question: str, sql: str,
    tables_used: list[str], columns_used: list[str],
    row_count: int, truncated: bool, assumptions: list[str],
    confidence_score: float, has_drivers: bool = True,
    causal_hint: bool | None = None,
) -> Validation:
    v = Validation()
    table_names = [t.split(".")[-1].lower() for t in (tables_used or [])]
    used_cols = {c.lower() for c in (columns_used or [])}
    sql_l = (sql or "").lower()

    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()

    profiles = db.execute(
        select(ColumnProfile).where(
            ColumnProfile.connection_id == conn.id,
            ColumnProfile.table_name.in_(table_names) if table_names else False,
        )
    ).scalars().all() if table_names else []
    prof_by_col = {(p.table_name.lower(), p.column_name.lower()): p for p in profiles}

    # --- 1) Mesure : bon indicateur ? (piège HT/TTC) ---
    monetary = [p for p in profiles
                if re.search(r"amount|price|montant|revenue|ca\b|total|net", p.column_name, re.I)]
    used_monetary = [p for p in monetary if p.column_name.lower() in used_cols]
    if used_monetary:
        ttc_available = [p for p in monetary if re.search(r"ttc", p.column_name, re.I)]
        used_ttc = any(re.search(r"ttc", p.column_name, re.I) for p in used_monetary)
        chosen = ", ".join(sorted({p.column_name for p in used_monetary}))
        if ttc_available and not used_ttc:
            v.checks.append(Check(
                "measure", "Mesure monétaire", "warn",
                f"Mesure retenue : « {chosen} ». Une variante TTC existe "
                f"(« {ttc_available[0].column_name} ») — vérifier que le HT est bien voulu.",
            ))
        else:
            v.checks.append(Check(
                "measure", "Mesure monétaire", "pass",
                f"Mesure « {chosen} »" + (" (TTC)" if used_ttc else "") + " cohérente.",
            ))
        v.hypotheses.append(f"Mesure : {chosen}" + (" (TTC)" if used_ttc else ""))

    # --- 2) Cohérence des dates ---
    date_profiles = [p for p in profiles
                     if (p.detected_type in ("date", "datetime")
                         or re.search(r"date|_at$|jour|day", p.column_name, re.I))
                     and (p.column_name.lower() in used_cols or "group by" in sql_l)]
    date_issue = False
    for p in date_profiles:
        mx = _parse_date(p.max_value)
        if mx and mx > date.today():
            date_issue = True
            v.checks.append(Check(
                "dates", "Cohérence des dates", "warn",
                f"« {p.column_name} » contient des dates futures (max {p.max_value}) — "
                "possible saisie erronée ou données de test.",
            ))
            break
        if p.null_rate and p.null_rate >= 0.1:
            date_issue = True
            v.checks.append(Check(
                "dates", "Cohérence des dates", "warn",
                f"« {p.column_name} » a {p.null_rate*100:.0f}% de dates manquantes : "
                "la série temporelle porte sur une population partielle.",
            ))
            break
    if date_profiles and not date_issue:
        v.checks.append(Check("dates", "Cohérence des dates", "pass",
                              "Dates dans une plage plausible, peu de valeurs manquantes."))
        v.hypotheses.append(f"Date : {date_profiles[0].column_name}")

    # --- 3) Valeurs manquantes sur les colonnes mobilisées ---
    null_cols = [p for (t, c), p in prof_by_col.items()
                 if c in used_cols and p.null_rate and p.null_rate >= 0.3]
    if null_cols:
        worst = max(null_cols, key=lambda p: p.null_rate or 0)
        v.checks.append(Check(
            "nulls", "Valeurs manquantes", "warn",
            f"« {worst.column_name} » est vide à {worst.null_rate*100:.0f}% : "
            "le résultat porte sur une partie des lignes seulement.",
        ))
    elif used_cols:
        v.checks.append(Check("nulls", "Valeurs manquantes", "pass",
                              "Aucune colonne mobilisée n'a de taux de NULL préoccupant."))

    # --- 4) Duplication par jointure ---
    if " join " in f" {sql_l} " and snapshot is not None:
        rels = db.execute(
            select(DbRelation).where(
                DbRelation.snapshot_id == snapshot.id, DbRelation.status != "rejected"
            )
        ).scalars().all()
        fanout = [r for r in rels
                  if r.from_table.lower() in table_names and r.to_table.lower() in table_names
                  and (r.cardinality in ("1-n", "n-n"))]
        distinct = "distinct" in sql_l
        if fanout and _AGG.search(sql_l) and not distinct:
            r = fanout[0]
            v.checks.append(Check(
                "join_fanout", "Duplication de jointure", "warn",
                f"Jointure {r.from_table}→{r.to_table} de cardinalité {r.cardinality} + agrégat "
                "sans DISTINCT : des lignes ont pu être comptées plusieurs fois.",
            ))
        else:
            v.checks.append(Check("join_fanout", "Duplication de jointure", "pass",
                                  "Jointure sans risque de duplication détecté."))

    # --- 5) Plausibilité du nombre de lignes ---
    if row_count == 0:
        v.checks.append(Check("row_count", "Volume du résultat", "fail",
                              "Aucune ligne retournée — le résultat est vide."))
    elif truncated:
        v.checks.append(Check("row_count", "Volume du résultat", "warn",
                              "Résultat tronqué par le LIMIT automatique : total possiblement incomplet."))
    else:
        v.checks.append(Check("row_count", "Volume du résultat", "pass",
                              f"{row_count} ligne(s) — plausible."))

    # --- Hypothèses issues du moteur SQL (rendues explicites) ---
    for a in assumptions or []:
        if a not in v.hypotheses:
            v.hypotheses.append(a)

    # --- Facteurs de fiabilité (rapport entier, pas seulement le SQL) ---
    concept_statuses = set(db.execute(
        select(ConceptMapping.status).where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.table_name.in_(table_names) if table_names else False,
        )
    ).scalars().all()) if table_names else set()

    def factor(label: str, ok: bool, warn: bool = False):
        v.reliability_factors.append(
            {"label": label, "status": "ok" if ok else ("warn" if warn else "fail")}
        )

    factor("Concepts validés", bool(concept_statuses & {"validated", "corrected"}),
           warn=not concept_statuses)
    factor("Peu de NULL", not null_cols, warn=bool(null_cols))
    validated_rel = _has_validated_relation(db, snapshot, table_names) if snapshot else None
    if validated_rel is not None:
        factor("Relations validées", validated_rel, warn=not validated_rel)
    factor("Données récentes", not date_issue, warn=date_issue)
    factor("Hypothèses limitées", len(v.hypotheses) <= 1, warn=len(v.hypotheses) >= 2)

    # --- Score de fiabilité : confiance SQL pondérée par les contrôles ---
    score = confidence_score
    for c in v.checks:
        if c.status == "fail":
            score -= 0.20
        elif c.status == "warn":
            score -= 0.05
    score = max(0.0, min(1.0, score))
    v.reliability_percent = round(score * 100)
    v.reliability_stars = max(1, min(5, round(score * 5))) if row_count else 1

    # --- Verdict « je ne peux pas conclure » (causalité non établie) ---
    is_causal = causal_hint if causal_hint is not None else bool(_CAUSAL.search(question))
    if is_causal and not has_drivers:
        v.verdict = "cannot_conclude"
        v.verdict_note = (
            "Je constate le phénomène, mais je ne peux pas en déterminer la cause : "
            "les données disponibles ne permettent pas d'établir un lien de causalité."
        )

    return v


def _has_validated_relation(db: Session, snapshot, table_names: list[str]) -> bool | None:
    if snapshot is None or not table_names:
        return None
    rels = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    involved = [r for r in rels
                if r.from_table.lower() in table_names and r.to_table.lower() in table_names]
    if not involved:
        return None
    # « validées » = confirmées par un humain OU FK réellement déclarée en base.
    return any(r.status == "validated" or r.kind == "declared" for r in involved)
