"""Shared Pydantic models used across API, graph orchestration, UI, and evaluation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntentLabel(str, Enum):
    """Supported intent labels for incoming user queries."""

    research = "research"
    analysis = "analysis"
    planning = "planning"
    summarization = "summarization"
    other = "other"


class UserQuery(BaseModel):
    """Normalized input payload received from a user-facing channel."""

    query_id: str = Field(..., description="Unique query identifier")
    user_id: str = Field(..., description="End-user identifier")
    text: str = Field(..., min_length=1, description="Raw user prompt")
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IntentResult(BaseModel):
    """Result from intent-classification and routing stage."""

    label: IntentLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(default="")
    suggested_route: str = Field(..., description="Graph or handler name")


class PlanStep(BaseModel):
    """Single atomic step in an execution plan."""

    step_id: str
    description: str
    owner: str = Field(default="agent")
    status: str = Field(default="pending")


class Plan(BaseModel):
    """Plan for completing the user request."""

    plan_id: str
    objective: str
    steps: list[PlanStep] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """Evidence attached to findings or conclusions."""

    evidence_id: str
    source_type: str = Field(..., description="web, db, doc, human, etc.")
    source_ref: str = Field(..., description="URL, document id, or pointer")
    excerpt: str = Field(default="")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ResearchFinding(BaseModel):
    """Structured output from retrieval/research work."""

    finding_id: str
    statement: str
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CritiqueReport(BaseModel):
    """Self-critique or reviewer output over intermediate artifacts."""

    report_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    """User-facing response synthesized from findings and plan execution."""

    response_text: str
    key_points: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Evaluation metrics for quality, safety, and completion."""

    score_overall: float = Field(..., ge=0.0, le=1.0)
    score_factuality: float = Field(..., ge=0.0, le=1.0)
    score_helpfulness: float = Field(..., ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class WorkflowState(BaseModel):
    """End-to-end state object passed through the decision-intelligence workflow."""

    user_query: UserQuery
    intent: IntentResult | None = None
    plan: Plan | None = None
    findings: list[ResearchFinding] = Field(default_factory=list)
    critique: CritiqueReport | None = None
    synthesis: SynthesisOutput | None = None
    evaluation: EvaluationReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
