from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending_confirmation"


@dataclass
class ReviewResult:
    decision: ReviewDecision
    risk_level: RiskLevel
    reason: str
    original_command: str
    reviewed_by: str = "rule_engine"  # "rule_engine" | "ai_reviewer" | "user"
    suggested_alternative: Optional[str] = None
    metadata: dict = field(default_factory=dict)
