"""Typed workflow state definitions for the decision-intelligence graph."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


ApprovalStatus = Literal["pending", "approved", "rejected", "needs_revision"]


class WorkflowState(TypedDict, total=False):
    """Shared state object passed through graph nodes."""

    query: str
    intent: str
    plan: list[str]
    subtasks: list[dict[str, Any]]
    findings: dict[str, Any]
    critique: str
    approval_status: ApprovalStatus
    synthesis: str
    evaluation: dict[str, Any]
    execution_log: list[str]
    current_node: str
    timestamps: dict[str, str]
