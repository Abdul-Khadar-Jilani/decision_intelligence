from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workflows", tags=["workflows"])


@dataclass
class WorkflowEvent:
    sequence: int
    type: str
    message: str
    timestamp: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowRecord:
    workflow_id: str
    input_payload: dict[str, Any]
    state: Literal["pending", "running", "awaiting_approval", "completed", "failed"]
    created_at: str
    updated_at: str
    events: list[WorkflowEvent] = field(default_factory=list)
    output: dict[str, Any] | None = None
    error: str | None = None


class WorkflowStartRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    approved: bool
    note: str | None = None


class WorkflowRepository:
    def __init__(self, data_path: str | Path = "backend/api/routes/.workflow_store.json") -> None:
        self._path = Path(data_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._workflows: dict[str, WorkflowRecord] = {}
        self._approvals: dict[str, asyncio.Event] = {}
        self._subscriber_queues: dict[str, list[asyncio.Queue[WorkflowEvent | None]]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for item in data.get("workflows", []):
            events = [WorkflowEvent(**event) for event in item.get("events", [])]
            item["events"] = events
            record = WorkflowRecord(**item)
            self._workflows[record.workflow_id] = record

    def _dump(self) -> None:
        payload = {
            "workflows": [
                {
                    **{k: v for k, v in asdict(workflow).items() if k != "events"},
                    "events": [asdict(event) for event in workflow.events],
                }
                for workflow in self._workflows.values()
            ]
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    async def create(self, input_payload: dict[str, Any]) -> WorkflowRecord:
        async with self._lock:
            workflow_id = str(uuid4())
            timestamp = _utc_now()
            workflow = WorkflowRecord(
                workflow_id=workflow_id,
                input_payload=input_payload,
                state="pending",
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._workflows[workflow_id] = workflow
            self._approvals[workflow_id] = asyncio.Event()
            self._subscriber_queues.setdefault(workflow_id, [])
            self._append_event_unlocked(workflow_id, "created", "Workflow accepted", {"input": input_payload})
            self._dump()
            return workflow

    async def get(self, workflow_id: str) -> WorkflowRecord | None:
        async with self._lock:
            return self._workflows.get(workflow_id)

    async def append_event(self, workflow_id: str, event_type: str, message: str, data: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._append_event_unlocked(workflow_id, event_type, message, data or {})
            self._dump()

    def _append_event_unlocked(self, workflow_id: str, event_type: str, message: str, data: dict[str, Any]) -> None:
        workflow = self._workflows[workflow_id]
        event = WorkflowEvent(
            sequence=len(workflow.events) + 1,
            type=event_type,
            message=message,
            timestamp=_utc_now(),
            data=data,
        )
        workflow.events.append(event)
        workflow.updated_at = event.timestamp
        for queue in self._subscriber_queues.get(workflow_id, []):
            queue.put_nowait(event)

    async def set_state(self, workflow_id: str, state: Literal["pending", "running", "awaiting_approval", "completed", "failed"], *, output: dict[str, Any] | None = None, error: str | None = None) -> None:
        async with self._lock:
            workflow = self._workflows[workflow_id]
            workflow.state = state
            workflow.updated_at = _utc_now()
            workflow.output = output
            workflow.error = error
            self._dump()

    async def approve(self, workflow_id: str, approved: bool, note: str | None) -> WorkflowRecord:
        async with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                raise KeyError(workflow_id)
            if workflow.state != "awaiting_approval":
                raise ValueError("workflow is not awaiting approval")
            workflow.input_payload["approval"] = {"approved": approved, "note": note}
            self._append_event_unlocked(
                workflow_id,
                "approval_received",
                "Approval decision received",
                {"approved": approved, "note": note},
            )
            if approved:
                self._approvals[workflow_id].set()
            else:
                workflow.state = "failed"
                workflow.error = note or "Rejected by reviewer"
                workflow.updated_at = _utc_now()
            self._dump()
            return workflow

    async def subscribe(self, workflow_id: str) -> asyncio.Queue[WorkflowEvent | None]:
        async with self._lock:
            if workflow_id not in self._workflows:
                raise KeyError(workflow_id)
            queue: asyncio.Queue[WorkflowEvent | None] = asyncio.Queue()
            self._subscriber_queues.setdefault(workflow_id, []).append(queue)
            return queue

    async def unsubscribe(self, workflow_id: str, queue: asyncio.Queue[WorkflowEvent | None]) -> None:
        async with self._lock:
            subscribers = self._subscriber_queues.get(workflow_id, [])
            if queue in subscribers:
                subscribers.remove(queue)

    async def release_subscribers(self, workflow_id: str) -> None:
        async with self._lock:
            for queue in self._subscriber_queues.get(workflow_id, []):
                queue.put_nowait(None)

    async def wait_for_approval(self, workflow_id: str) -> None:
        await self._approvals[workflow_id].wait()


repository = WorkflowRepository()


@router.post("")
async def start_workflow(payload: WorkflowStartRequest) -> dict[str, Any]:
    workflow = await repository.create(payload.input)
    asyncio.create_task(_run_workflow(workflow.workflow_id))
    return {
        "workflow_id": workflow.workflow_id,
        "state": workflow.state,
        "created_at": workflow.created_at,
    }


@router.get("/{workflow_id}")
async def get_workflow_state(workflow_id: str) -> dict[str, Any]:
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {
        "workflow_id": workflow.workflow_id,
        "state": workflow.state,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "error": workflow.error,
    }


@router.get("/{workflow_id}/events")
async def get_workflow_events(workflow_id: str, stream: bool = False) -> Any:
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")

    if not stream:
        return {
            "workflow_id": workflow.workflow_id,
            "events": [asdict(event) for event in workflow.events],
        }

    async def event_stream() -> Any:
        queue = await repository.subscribe(workflow_id)
        try:
            snapshot = await repository.get(workflow_id)
            if snapshot is not None:
                for event in snapshot.events:
                    yield f"event: {event.type}\ndata: {json.dumps(asdict(event))}\n\n"
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"event: {event.type}\ndata: {json.dumps(asdict(event))}\n\n"
        finally:
            await repository.unsubscribe(workflow_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{workflow_id}/approval")
async def approve_workflow(workflow_id: str, request: ApprovalRequest) -> dict[str, Any]:
    try:
        workflow = await repository.approve(workflow_id, request.approved, request.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="workflow not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return {
        "workflow_id": workflow.workflow_id,
        "state": workflow.state,
        "updated_at": workflow.updated_at,
    }


@router.get("/{workflow_id}/output")
async def get_workflow_output(workflow_id: str) -> dict[str, Any]:
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    if workflow.state != "completed":
        raise HTTPException(status_code=409, detail="workflow is not completed")
    return {
        "workflow_id": workflow.workflow_id,
        "output": workflow.output,
        "updated_at": workflow.updated_at,
    }


async def _run_workflow(workflow_id: str) -> None:
    try:
        await repository.set_state(workflow_id, "running")
        await repository.append_event(workflow_id, "running", "Workflow started")

        await asyncio.sleep(0.2)
        await repository.append_event(workflow_id, "step_completed", "Input validated")

        await asyncio.sleep(0.2)
        await repository.set_state(workflow_id, "awaiting_approval")
        await repository.append_event(workflow_id, "approval_required", "Manual approval required")

        await repository.wait_for_approval(workflow_id)
        await repository.set_state(workflow_id, "running")
        await repository.append_event(workflow_id, "running", "Workflow resumed after approval")

        await asyncio.sleep(0.2)
        record = await repository.get(workflow_id)
        result = {
            "echo": (record.input_payload if record else {}),
            "message": "Workflow completed successfully",
        }
        await repository.set_state(workflow_id, "completed", output=result)
        await repository.append_event(workflow_id, "completed", "Workflow completed", {"output": result})
    except Exception as exc:  # pragma: no cover - defensive catch for background task
        await repository.set_state(workflow_id, "failed", error=str(exc))
        await repository.append_event(workflow_id, "failed", "Workflow failed", {"error": str(exc)})
    finally:
        await repository.release_subscribers(workflow_id)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
