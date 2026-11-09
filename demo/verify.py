#!/usr/bin/env python3
"""Runner de vérification d'un scénario de la bibliothèque de démonstration.

Rejoue le pipeline complet — Discover → Understand → Reason → Reveal — et imprime
ce que le moteur PRODUIT RÉELLEMENT, à comparer au Gold Standard écrit à la main
(demo/<scenario>/gold_standard.md).

    cd backend && python ../demo/verify.py retail
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _runner import SCENARIO_QUESTIONS, analyze  # noqa: E402


def _question(scenario: str) -> str | None:
    """Question du scénario : map des scénarios de base, sinon expected.json
    (scénarios imbriqués comme challenge/xxx)."""
    if scenario in SCENARIO_QUESTIONS:
        return SCENARIO_QUESTIONS[scenario]
    exp = HERE / scenario / "expected.json"
    if exp.exists():
        return json.loads(exp.read_text(encoding="utf-8")).get("question")
    return None


def _bar(title: str) -> None:
    print("\n" + "═" * 78 + f"\n {title}\n" + "═" * 78)


def main(scenario: str) -> None:
    question = _question(scenario)
    if question is None:
        print(f"Scénario inconnu : {scenario}. Connus : {', '.join(SCENARIO_QUESTIONS)} "
              f"(+ challenge/<nom>).")
        sys.exit(1)
    r, meta = analyze(scenario, question)

    _bar(f"DISCOVER / UNDERSTAND — noreon_demo_{scenario}")
    print(f"Lecture seule vérifiée : {meta['read_only']}")
    print(f"Tables : {meta['tables']} · Relations (dont FK implicites) : {meta['relations']}")

    _bar(f"REASON + REVEAL — « {question} »")
    print(f"Statut          : {r.status}")
    print(f"Intention       : {r.intent}  →  {r.intent_restated}")
    print(f"\nMessage :\n{r.message}")

    inv = r.investigation
    if inv:
        print(f"\nSujet / mesure  : {inv['subject']} · {inv['metric_label']}")
        if r.chronicle:
            print(f"\nChronologie     : {r.chronicle['narrative']}")
        print("\nFacteurs dominants (drivers) :")
        for d in inv.get("drivers_struct", []):
            print(f"  • {d['dimension']} → « {d['segment']} » : {d['share']}%")
        for rev in inv.get("revisions", []):
            print(f"\nChangement d'avis :\n  ↻ {rev}")
        print(f"\nConclusion      : {inv.get('conclusion', '')}")

    if r.self_critique:
        print("\nAuto-critique :")
        for c in r.self_critique:
            print(f"  ⚖ Cette analyse {c}.")

    if r.decisions:
        print("\nDecision Engine :")
        print(f"  Objectif reformulé : {r.decisions['restated']}")
        for x in r.decisions["decisions"]:
            imp = f" · impact {x['impact']}" if x.get("impact") else ""
            print(f"  {'★' * x.get('stars', 3)} {x['role']} — {x['recommendation']}{imp}")
        if r.decisions.get("inaction"):
            print(f"  ⏳ Inaction : {r.decisions['inaction']}")

    if r.serendipity:
        print(f"\nSérendipité     : {r.serendipity['title']} — {r.serendipity['detail']}")
    if r.confidence:
        print(f"\nConfiance       : {r.confidence.get('score')} / 100")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "retail")
