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
    print(f"  cas dont les faits ont changé             {len(comparison['changed_cases'])}")
    if args.json_output:
        args.json_output.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Détail JSON : {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
