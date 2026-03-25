"""Workflow routes for human-in-the-loop checkpoint control."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, MutableMapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workflows", tags=["workflows"])

# Placeholder in-memory stores. In production wire these through dependency
# injection to durable storage and a real workflow runner.
WORKFLOW_CHECKPOINTS: Dict[str, Dict[str, Any]] = {}
WORKFLOW_RUNS: Dict[str, Dict[str, Any]] = {}


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REFINE = "request_refine"


class DecisionRequest(BaseModel):
    reviewer: str | None = Field(default=None, description="Reviewer identity")
    comment: str | None = Field(default=None, description="Decision rationale")


class ResumeRequest(BaseModel):
    input_patch: Dict[str, Any] | None = Field(
        default=None,
        description="Optional state patch to merge into checkpoint before resume",
    )


class WorkflowDecisionResponse(BaseModel):
    checkpoint_id: str
    workflow_id: str | None = None
    run_id: str | None = None
    decision: ApprovalDecision
    resumed: bool = False


@router.post("/{checkpoint_id}/approve", response_model=WorkflowDecisionResponse)
def approve_workflow(checkpoint_id: str, payload: DecisionRequest) -> WorkflowDecisionResponse:
    return _apply_human_decision(checkpoint_id, ApprovalDecision.APPROVE, payload)


@router.post("/{checkpoint_id}/reject", response_model=WorkflowDecisionResponse)
def reject_workflow(checkpoint_id: str, payload: DecisionRequest) -> WorkflowDecisionResponse:
    return _apply_human_decision(checkpoint_id, ApprovalDecision.REJECT, payload)


@router.post("/{checkpoint_id}/request_refine", response_model=WorkflowDecisionResponse)
def request_refine_workflow(checkpoint_id: str, payload: DecisionRequest) -> WorkflowDecisionResponse:
    return _apply_human_decision(checkpoint_id, ApprovalDecision.REQUEST_REFINE, payload)


@router.post("/{checkpoint_id}/resume", response_model=WorkflowDecisionResponse)
def resume_workflow_from_checkpoint(checkpoint_id: str, payload: ResumeRequest) -> WorkflowDecisionResponse:
    checkpoint = _get_checkpoint_or_404(checkpoint_id)

    if payload.input_patch:
        checkpoint.update(payload.input_patch)

    checkpoint["checkpoint_status"] = "resumed"
    checkpoint["resumed_at"] = datetime.now(timezone.utc).isoformat()

    run_id = checkpoint.get("run_id")
    if run_id:
        WORKFLOW_RUNS[run_id] = checkpoint

    return WorkflowDecisionResponse(
        checkpoint_id=checkpoint_id,
        workflow_id=checkpoint.get("workflow_id"),
        run_id=run_id,
        decision=checkpoint.get("human_decision", ApprovalDecision.APPROVE),
        resumed=True,
    )


def _apply_human_decision(
    checkpoint_id: str,
    decision: ApprovalDecision,
    payload: DecisionRequest,
) -> WorkflowDecisionResponse:
    checkpoint = _get_checkpoint_or_404(checkpoint_id)

    checkpoint["human_decision"] = decision
    checkpoint["human_feedback"] = {
        "reviewer": payload.reviewer,
        "comment": payload.comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint["checkpoint_status"] = "decision_recorded"

    return WorkflowDecisionResponse(
        checkpoint_id=checkpoint_id,
        workflow_id=checkpoint.get("workflow_id"),
        run_id=checkpoint.get("run_id"),
        decision=decision,
        resumed=False,
    )


def _get_checkpoint_or_404(checkpoint_id: str) -> MutableMapping[str, Any]:
    checkpoint = WORKFLOW_CHECKPOINTS.get(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_id}' was not found")
    return checkpoint
