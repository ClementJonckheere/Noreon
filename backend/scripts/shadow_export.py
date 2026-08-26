#!/usr/bin/env python3
"""Exporte une baseline read-only de ``planner_shadow_evaluations``.

Exemple, depuis ``backend/`` :

  python scripts/shadow_export.py --expect-count 32 --output shadow_before_p0.json

Par défaut, aucune question textuelle n'est exportée. Le corpus de campagne est
rapproché par HMAC et identifié uniquement par son ordinal et sa famille.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.shadow.export import build_export, latest_rows  # noqa: E402
from app.core.config import settings                              # noqa: E402
from app.core.db import SessionLocal                              # noqa: E402
from shadow_campaign import _questions                           # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("shadow_baseline.json"))
    parser.add_argument("--expect-count", type=int, default=32)
    parser.add_argument("--tenant", type=int, default=None)
    parser.add_argument("--questions-file", default=None)
    parser.add_argument(
        "--include-sanitized-question",
        action="store_true",
        help="inclut question_sanitized si son stockage opt-in était activé",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        rows = latest_rows(session, limit=args.expect_count, tenant_id=args.tenant)
    try:
        payload = build_export(
            rows,
            questions=_questions(args.questions_file),
            secret_key=settings.secret_key,
            expected_count=args.expect_count,
            include_sanitized_question=args.include_sanitized_question,
        )
    except ValueError as exc:
        print(f"Export refusé : {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Baseline exportée : {args.output} · {payload['row_count']} observations · "
        f"{payload['matched_campaign_cases']} cas de campagne reconnus · "
        "0 question brute"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
