"""planner shadow evaluations (C5 shadow planner telemetry)

Domaine de persistance séparé : SEULE table créée pour le shadow. `analysis_plans`
et `analysis_runs` ne sont pas créées ici → pollution de l'historique décisionnel
physiquement impossible.

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planner_shadow_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("question_sanitized", sa.String(), nullable=True),
        sa.Column("planner_mode", sa.String(length=16), nullable=False),
        sa.Column("sample_rate", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("candidate_model", sa.String(length=64), nullable=True),
        sa.Column("routing_reason", sa.String(), nullable=True),
        sa.Column("routing_matched_rule", sa.String(length=128), nullable=True),
        sa.Column("routing_tier", sa.String(length=16), nullable=True),
        sa.Column("escalated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("previous_model", sa.String(length=64), nullable=True),
        sa.Column("escalation_reason", sa.String(), nullable=True),
        sa.Column("interpretation_schema_version", sa.String(length=16), nullable=True),
        sa.Column("goal_types_version", sa.String(length=16), nullable=True),
        sa.Column("router_version", sa.String(length=16), nullable=True),
        sa.Column("planner_prompt_version", sa.String(length=16), nullable=True),
        sa.Column("comparator_version", sa.String(length=16), nullable=True),
        sa.Column("projection_version", sa.String(length=16), nullable=True),
        sa.Column("llm_status", sa.String(length=24), server_default="skipped", nullable=False),
        sa.Column("fallback_status", sa.String(length=24), nullable=True),
        sa.Column("llm_plan_json", sa.JSON(), nullable=True),
        sa.Column("llm_projection_json", sa.JSON(), nullable=True),
        sa.Column("fallback_projection_json", sa.JSON(), nullable=True),
        sa.Column("plan_purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comparison_outcome", sa.String(length=24), nullable=True),
        sa.Column("comparison_json", sa.JSON(), nullable=True),
        sa.Column("repair_applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("repair_type", sa.String(length=32), nullable=True),
        sa.Column("repair_details_json", sa.JSON(), nullable=True),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("fallback_latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_prompt", sa.Integer(), nullable=True),
        sa.Column("tokens_completion", sa.Integer(), nullable=True),
        sa.Column("tokens_total", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("error_kind", sa.String(length=24), nullable=True),
        sa.Column("error_detail", sa.String(), nullable=True),
        sa.Column("review_status", sa.String(length=24), server_default="none", nullable=False),
    )
    op.create_index("ix_pse_tenant_created", "planner_shadow_evaluations", ["tenant_id", "created_at"])
    op.create_index("ix_pse_request_id", "planner_shadow_evaluations", ["request_id"])
    op.create_index("ix_pse_outcome", "planner_shadow_evaluations", ["comparison_outcome"])
    op.create_index("ix_pse_candidate_model", "planner_shadow_evaluations", ["candidate_model"])
    op.create_index("ix_pse_llm_status", "planner_shadow_evaluations", ["llm_status"])
    op.create_index("ix_pse_repair_applied", "planner_shadow_evaluations", ["repair_applied"])


def downgrade() -> None:
    for ix in ("ix_pse_repair_applied", "ix_pse_llm_status", "ix_pse_candidate_model",
               "ix_pse_outcome", "ix_pse_request_id", "ix_pse_tenant_created"):
        op.drop_index(ix, table_name="planner_shadow_evaluations")
    op.drop_table("planner_shadow_evaluations")
