"""measurement plans and runs (action outcome measurement)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "measurement_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.Integer(), sa.ForeignKey("decision_records.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), index=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("measure_type", sa.String(length=16), nullable=False, server_default="impact"),
        sa.Column("metric_concept_id", sa.String(length=64), nullable=False, server_default="revenue"),
        sa.Column("metric_label", sa.String(length=128), nullable=False, server_default="Chiffre d'affaires"),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("control_scope", sa.JSON(), nullable=True),
        sa.Column("comparison", sa.String(length=24), nullable=False, server_default="matched_control"),
        sa.Column("baseline_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("observation_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0.02"),
        sa.Column("protocol_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_target", sa.Float(), nullable=True),
        sa.Column("baseline_control", sa.Float(), nullable=True),
        sa.Column("baseline_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_sql", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "measurement_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("measurement_plans.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("baseline_target", sa.Float(), nullable=True),
        sa.Column("baseline_control", sa.Float(), nullable=True),
        sa.Column("observed_target", sa.Float(), nullable=True),
        sa.Column("observed_control", sa.Float(), nullable=True),
        sa.Column("raw_delta", sa.Float(), nullable=True),
        sa.Column("control_delta", sa.Float(), nullable=True),
        sa.Column("adjusted_delta", sa.Float(), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=False, server_default="inconclusif"),
        sa.Column("limitations", sa.JSON(), nullable=True),
        sa.Column("observation_sql", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("measurement_runs")
    op.drop_table("measurement_plans")
