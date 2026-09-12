"""
Aegis — Storage ORM Models

Exports all declarative models to ensure metadata registration for Alembic.
"""

from storage.models.base import Base
from storage.models.eligibility_decision import EligibilityDecision
from storage.models.match_score import MatchScore
from storage.models.notification import Notification
from storage.models.opportunity import Opportunity
from storage.models.profile import Profile
from storage.models.raw_snapshot import RawSnapshot
from storage.models.repair import RepairPatch, RepairRun
from storage.models.source import Source
from storage.models.source_run import SourceRun

__all__ = [
    "Base",
    "EligibilityDecision",
    "MatchScore",
    "Notification",
    "Opportunity",
    "Profile",
    "RawSnapshot",
    "RepairPatch",
    "RepairRun",
    "Source",
    "SourceRun",
]

