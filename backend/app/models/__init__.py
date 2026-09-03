"""Modèles de la base interne Noreon.

Import centralisé pour qu'Alembic voie toutes les tables via Base.metadata.
"""
from app.models.alert import Alert, AlertEvent
from app.models.connection import Connection
from app.models.conversation import (
    Conversation,
    ConversationFolder,
    ConversationTurn,
)
from app.models.decision import DecisionRecord
from app.models.definitions import BusinessDefinition
from app.models.insight import InsightBaseline
from app.models.profile import ColumnProfile, ProfilingJob
from app.models.reasoning import ReasoningMemory
from app.models.quality import QualityScore
from app.models.query_log import QueryLog
from app.models.schema_catalog import (
    DbColumn,
    DbRelation,
    DbTable,
    SchemaSnapshot,
)
from app.models.report import Report, ReportBlock
from app.models.semantic import BusinessConcept, ConceptMapping
from app.models.concept_definition import ConceptDefinition
from app.models.concept_arbitration import ConceptArbitration, ConceptReference
from app.models.relation_candidate import RelationCandidate
from app.models.work_item import ActivityEvent, WorkItem
from app.models.space import (
    Space,
    SpaceColumnAccess,
    SpaceConnection,
    SpaceMember,
    SpaceTableAccess,
)
from app.models.tenant import Tenant, TenantSettings
from app.models.user import ConnectionAccess, User

__all__ = [
    "Tenant",
    "TenantSettings",
    "Connection",
    "SchemaSnapshot",
    "DbTable",
    "DbColumn",
    "DbRelation",
    "ColumnProfile",
    "ProfilingJob",
    "QualityScore",
    "QueryLog",
    "InsightBaseline",
    "ReasoningMemory",
    "BusinessConcept",
    "ConceptMapping",
    "ConceptDefinition",
    "ConceptReference",
    "ConceptArbitration",
    "RelationCandidate",
    "WorkItem",
    "ActivityEvent",
    "BusinessDefinition",
    "DecisionRecord",
    "Alert",
    "AlertEvent",
    "Conversation",
    "ConversationFolder",
    "ConversationTurn",
    "Report",
    "ReportBlock",
    "Space",
    "SpaceConnection",
    "SpaceMember",
    "SpaceTableAccess",
    "SpaceColumnAccess",
    "User",
    "ConnectionAccess",
]
