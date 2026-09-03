"""shadow C6 telemetry : three stages + analytical safety

Ajoute à planner_shadow_evaluations les étages capability_resolution / resolved_plan
/ legacy_execution_projection, le résumé des états capability, et la sécurité
analytique. Aucun recalcul rétroactif des observations C5 existantes.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa


revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    t = "planner_shadow_evaluations"
    op.add_column(t, sa.Column("capability_resolution_json", sa.JSON(), nullable=True))
    op.add_column(t, sa.Column("resolved_plan_json", sa.JSON(), nullable=True))
    op.add_column(t, sa.Column("legacy_execution_projection_json", sa.JSON(), nullable=True))
    op.add_column(t, sa.Column("capability_states_json", sa.JSON(), nullable=True))
    op.add_column(t, sa.Column("analytical_safety", sa.String(length=24), nullable=True))
    op.add_column(t, sa.Column("analytical_safety_json", sa.JSON(), nullable=True))
    op.add_column(t, sa.Column("analytical_safety_version", sa.String(length=16), nullable=True))
    op.create_index("ix_pse_safety", t, ["analytical_safety"])


def downgrade() -> None:
    t = "planner_shadow_evaluations"
    op.drop_index("ix_pse_safety", table_name=t)
    for col in ("analytical_safety_version", "analytical_safety_json", "analytical_safety",
                "capability_states_json", "legacy_execution_projection_json",
                "resolved_plan_json", "capability_resolution_json"):
        op.drop_column(t, col)
