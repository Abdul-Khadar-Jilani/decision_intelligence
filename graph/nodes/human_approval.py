"""Human approval node utilities.

This module builds and persists a human-approval request payload containing
planner output, findings, and critic concerns before execution pauses.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, MutableMapping

CHECKPOINT_WAITING_FOR_APPROVAL = "waiting_for_human_approval"


def _as_list(value: Any) -> list[Any]:
    """Normalize values to a list for summary fields."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_approval_request_payload(state: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a payload that captures key context for human review.

    Expected state keys (all optional):
      - workflow_id
      - run_id
      - plan
      - findings
      - critic_concerns
      - critic_feedback
    """
    critic_concerns = _as_list(state.get("critic_concerns") or state.get("critic_feedback"))

    return {
        "kind": "human_approval_request",
        "workflow_id": state.get("workflow_id"),
        "run_id": state.get("run_id"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "plan": deepcopy(state.get("plan")),
            "findings": deepcopy(state.get("findings")),
            "critic_concerns": deepcopy(critic_concerns),
        },
        "status": "pending",
    }


def persist_checkpoint_before_wait(
    state: MutableMapping[str, Any],
    *,
    checkpoint_store: MutableMapping[str, Any],
    checkpoint_id: str | None = None,
) -> str:
    """Persist checkpoint state before pausing for human approval.

    This mutates ``state`` to include ``approval_request``,
    ``checkpoint_status``, and ``checkpoint_id``.
    """
    payload = build_approval_request_payload(state)
    resolved_checkpoint_id = checkpoint_id or state.get("run_id") or state.get("workflow_id")
    if not resolved_checkpoint_id:
        raise ValueError("Cannot persist checkpoint without run_id, workflow_id, or explicit checkpoint_id")

    checkpoint_snapshot = deepcopy(dict(state))
    checkpoint_snapshot["approval_request"] = payload
    checkpoint_snapshot["checkpoint_status"] = CHECKPOINT_WAITING_FOR_APPROVAL
    checkpoint_snapshot["checkpoint_id"] = resolved_checkpoint_id

    checkpoint_store[resolved_checkpoint_id] = checkpoint_snapshot

    state["approval_request"] = payload
    state["checkpoint_status"] = CHECKPOINT_WAITING_FOR_APPROVAL
    state["checkpoint_id"] = resolved_checkpoint_id

    return resolved_checkpoint_id
