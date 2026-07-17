"""Agent Analyste hors-ligne (Module 10 — Rapport IA).

Produit un rapport structuré (résumé, observations, anomalies,
recommandations) par CALCUL sur les résultats — tendances, valeurs
aberrantes, concentration — sans dépendre d'un LLM. Les fournisseurs LLM
peuvent enrichir l'interprétation ; cet analyste garantit un socle chiffré,
vérifiable, et fonctionne hors-ligne.

Reçoit des données déjà passées par le Privacy Engine (les identités sont
pseudonymisées, les mesures inchangées).
"""
from __future__ import annotations

from statistics import mean, stdev

from app.llm.base import AnalysisResult
from app.services.charting import (
    _classify,
    _is_number,
    _is_numeric_str,
    _sorted_monotonic,
)


def _num(v) -> float:
    if isinstance(v, str):
        return float(v.replace(",", "."))
    return float(v)


def analyze(question: str, columns: list[str], rows: list[list]) -> AnalysisResult:
    n = len(rows)
    if n == 0:
        return AnalysisResult(
            summary="La requête n'a retourné aucune ligne.",
            observations=["Le périmètre filtré est peut-être trop restrictif."],
            recommendations=["Élargissez la période ou retirez un filtre."],
        )

    # Agrégat mono-cellule.
    if n == 1 and len(columns) == 1 and (_is_number(rows[0][0]) or _is_numeric_str(rows[0][0])):
        return AnalysisResult(
            summary=f"Résultat : {columns[0]} = {rows[0][0]}.",
            observations=["Valeur agrégée unique, sans ventilation."],
        )

    kinds = _classify(columns, rows)
    # Une colonne temporelle n'est traitée comme SÉRIE que si elle est ordonnée
    # (résultat d'un GROUP BY … ORDER BY). Sinon (dump brut), on ne calcule pas
    # de tendance ni de rupture « entre périodes » — ce serait décoratif et faux.
    temporal = [
        c for c in columns
        if kinds[c] == "temporal" and _sorted_monotonic([r[columns.index(c)] for r in rows])
    ]
    numeric = [c for c in columns if kinds[c] == "numeric"]
    categorical = [c for c in columns if kinds[c] == "categorical"]

    observations: list[str] = [f"{n} ligne(s), {len(columns)} colonne(s)."]
    anomalies: list[str] = []
    recommendations: list[str] = []
    summary = f"{n} enregistrement(s) correspondant à la question."

    if numeric:
        ycol = numeric[0]
        yi = columns.index(ycol)
        try:
            values = [_num(r[yi]) for r in rows if r[yi] is not None]
        except (TypeError, ValueError):
            values = []

        if len(values) >= 3:
            total = sum(values)
            avg = mean(values)

            # --- Série temporelle : tendance + ruptures ---
            if temporal:
                xi = columns.index(temporal[0])
                first, last = values[0], values[-1]
                if first:
                    change = (last - first) / abs(first) * 100
                    direction = "hausse" if change > 5 else ("baisse" if change < -5 else "stabilité")
                    summary = (
                        f"{direction.capitalize()} de {ycol} sur la période : "
                        f"{first:,.0f} → {last:,.0f} ({change:+.0f}%)."
                    )
                imax, imin = values.index(max(values)), values.index(min(values))
                observations.append(
                    f"Maximum {max(values):,.0f} ({rows[imax][xi]}), "
                    f"minimum {min(values):,.0f} ({rows[imin][xi]})."
                )
                # Rupture entre périodes consécutives (> 30 %).
                for i in range(1, len(values)):
                    prev = values[i - 1]
                    if prev and abs(values[i] - prev) / abs(prev) > 0.30:
                        pct = (values[i] - prev) / abs(prev) * 100
                        anomalies.append(
                            f"Variation brutale de {ycol} en {rows[i][xi]} : "
                            f"{prev:,.0f} → {values[i]:,.0f} ({pct:+.0f}%)."
                        )
                if anomalies:
                    recommendations.append(
                        "Vérifiez les périodes signalées : données incomplètes "
                        "(période en cours ?) ou événement métier réel."
                    )

            # --- Catégories : concentration ---
            elif categorical:
                xi = columns.index(categorical[0])
                imax = values.index(max(values))
                share = max(values) / total * 100 if total else 0
                summary = (
                    f"« {rows[imax][xi]} » domine avec {max(values):,.0f} "
                    f"({share:.0f}% du total {total:,.0f})."
                )
                if share > 50 and len(values) > 2:
                    observations.append(
                        f"Forte concentration : la première catégorie pèse {share:.0f}% du total."
                    )
                    recommendations.append(
                        "Une dépendance à une catégorie dominante est un risque : "
                        "surveillez son évolution spécifiquement."
                    )
                spread = max(values) / min(values) if min(values) else None
                if spread and spread > 10:
                    observations.append(
                        f"Écart important entre catégories (rapport max/min ≈ {spread:.0f}×)."
                    )

            # --- Valeurs aberrantes (> 2σ) ---
            if len(values) >= 8:
                sd = stdev(values)
                if sd > 0:
                    outliers = [
                        (i, v) for i, v in enumerate(values) if abs(v - avg) > 2 * sd
                    ]
                    for i, v in outliers[:3]:
                        label = rows[i][columns.index(temporal[0])] if temporal else (
                            rows[i][columns.index(categorical[0])] if categorical else f"ligne {i + 1}"
                        )
                        anomalies.append(
                            f"Valeur atypique de {ycol} : {v:,.0f} ({label}), "
                            f"à plus de 2 écarts-types de la moyenne ({avg:,.0f})."
                        )

    return AnalysisResult(
        summary=summary,
        observations=observations,
        anomalies=anomalies,
        recommendations=recommendations,
    )
