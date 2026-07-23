"""Contexte d'entreprise — la mémoire des conventions d'analyse.

Chaque entreprise a des habitudes : « on raisonne au mois », « toujours en TTC »,
« France uniquement », « hors magasins de test ». Noreon les connaît et **ne les
redemande plus** :

- elles sont **injectées dans le contexte** du moteur SQL (il les respecte) ;
- elles apparaissent comme **hypothèses retenues** dans chaque rapport (la
  relecture les rend visibles).

Rien d'identifiant ici — que des conventions métier, propres au tenant.
"""
from __future__ import annotations

_GRAIN_LABEL = {
    "month": "mensuelle", "week": "hebdomadaire", "day": "quotidienne",
    "quarter": "trimestrielle", "year": "annuelle",
}
_DEFAULT = {"amount_basis": None, "period_grain": None, "conventions": []}


def get_context(settings) -> dict:
    raw = getattr(settings, "analysis_context", None)
    ctx = dict(_DEFAULT)
    if isinstance(raw, dict):
        ctx.update({k: raw.get(k, ctx[k]) for k in ctx})
    if not isinstance(ctx.get("conventions"), list):
        ctx["conventions"] = []
    return ctx


def context_block(ctx: dict) -> str:
    """Bloc texte injecté dans le contexte du moteur SQL (lisible par un LLM)."""
    lines: list[str] = []
    if ctx.get("amount_basis"):
        lines.append(f"  - Montants : {ctx['amount_basis']}")
    if ctx.get("period_grain"):
        lines.append(f"  - Granularité temporelle par défaut : {ctx['period_grain']}")
    for c in ctx.get("conventions", []):
        if c:
            lines.append(f"  - {c}")
    if not lines:
        return ""
    return "Contexte entreprise (conventions à respecter, sans les redemander) :\n" + "\n".join(lines)


def as_hypotheses(ctx: dict) -> list[str]:
    """Conventions rendues visibles comme « hypothèses retenues » dans le rapport."""
    hyp: list[str] = []
    if ctx.get("amount_basis"):
        hyp.append(f"Montants en {ctx['amount_basis']}")
    if ctx.get("period_grain"):
        grain = _GRAIN_LABEL.get(ctx["period_grain"], ctx["period_grain"])
        hyp.append(f"Analyse {grain}")
    hyp.extend(c for c in ctx.get("conventions", []) if c)
    return hyp
