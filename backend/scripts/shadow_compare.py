#!/usr/bin/env python3
"""Compare deux exports des mêmes cas shadow, avant/après un changement."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.shadow.compare_exports import compare_exports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    try:
        comparison = compare_exports(before, after)
    except ValueError as exc:
        print(f"Comparaison refusée : {exc}", file=sys.stderr)
        return 2

    print(f"SHADOW AVANT/APRÈS — {comparison['case_count']} cas identiques")
    for key, label in (
        ("required_unresolved_supported", "unresolved requis encore SUPPORTED"),
        ("supported_compile_violations", "SUPPORTED sans compile_ready"),
        ("supported_compile_ready", "goals SUPPORTED compile-ready"),
        ("covers_question", "questions déclarées couvertes"),
    ):
        before_value = comparison["before"][key]
        after_value = comparison["after"][key]
        print(f"  {label:<40} {before_value:>3} → {after_value:<3} "
              f"(Δ {comparison['deltas'][key]:+d})")
    before_semantic = comparison["before"]["goal_semantic_completeness"]
    after_semantic = comparison["after"]["goal_semantic_completeness"]
    print("\nP0-C ACCEPTANCE")
    print("  goal semantic completeness              "
          f"{before_semantic['complete']}/{before_semantic['total']} "
          f"({before_semantic['rate']:.1%}) → "
          f"{after_semantic['complete']}/{after_semantic['total']} "
          f"({after_semantic['rate']:.1%})")
    for key, label in (
        ("goal_without_operand_and_without_reason", "goal sans opérande/raison"),
        ("diagnostic_cascade_count", "diagnostics cascade"),
        ("known_refs_false_unresolved", "known refs false unresolved"),
        ("resolved_semantic_ready_goals", "goals sémantiquement résolus"),
        ("compile_ready_goals", "goals compile-ready"),
        ("required_unresolved", "unresolved required"),
        ("optional_unresolved", "unresolved optional"),
        ("aggregation_contradictions", "contradictions agrégation"),
        ("contract_errors", "contract errors"),
        ("provider_errors", "provider errors"),
        ("repairs", "repairs"),
    ):
        before_value = comparison["before"][key]
        after_value = comparison["after"][key]
        print(f"  {label:<40} {before_value:>3} → {after_value:<3} "
              f"(Δ {comparison['deltas'][key]:+d})")
    print(f"  goal statuses                           "
          f"{comparison['before']['goal_statuses']} → {comparison['after']['goal_statuses']}")
    print(f"  relations constraint exécutables        "
          f"{comparison['before']['relations_constraint_present']} → "
          f"{comparison['after']['relations_constraint_present']}")
    print(f"  relations inferred ignorées             "
          f"{comparison['before']['relations_inferred_nonvalidated_ignored']} → "
          f"{comparison['after']['relations_inferred_nonvalidated_ignored']}")
    print(f"  cas dont les faits ont changé             {len(comparison['changed_cases'])}")
    if args.json_output:
        args.json_output.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Détail JSON : {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
