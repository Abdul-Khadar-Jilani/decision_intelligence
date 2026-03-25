from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import time
import uuid

from .execution_log import append_trace


@dataclass(frozen=True)
class RetryPolicy:
    """Defines retry behavior for tool calls."""

    max_attempts: int = 2
    backoff_seconds: float = 0.25
    exponential_backoff: bool = True
    retry_on_exceptions: tuple[type[Exception], ...] = (Exception,)


@dataclass(frozen=True)
class SourceAttribution:
    """Uniform source metadata returned by every tool output."""

    url: str
    source: str
    retrieved_at: str
    snippet: str
    confidence: float


@dataclass(frozen=True)
class ToolSpec:
    """Metadata and schemas used by orchestration/UI layers."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class ToolResult:
    """Standard result envelope for all tools."""

    ok: bool
    output: Dict[str, Any]
    sources: List[SourceAttribution]
    tool: str
    latency_ms: int
    error: Optional[str] = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "output": self.output,
            "sources": [asdict(source) for source in self.sources],
            "latency_ms": self.latency_ms,
            "error": self.error,
            "trace_id": self.trace_id,
        }


class BaseTool(ABC):
    """Tool contract with retry and trace logging baked in."""

    spec: ToolSpec

    def run(self, **kwargs: Any) -> ToolResult:
        started = time.perf_counter()
        policy = self.spec.retry_policy
        last_error: Optional[Exception] = None

        for attempt in range(1, policy.max_attempts + 1):
            try:
                result = self._run(**kwargs)
                result.latency_ms = int((time.perf_counter() - started) * 1000)
                append_trace(result.to_dict())
                return result
            except policy.retry_on_exceptions as exc:
                last_error = exc
                if attempt == policy.max_attempts:
                    break
                delay = policy.backoff_seconds
                if policy.exponential_backoff:
                    delay *= 2 ** (attempt - 1)
                time.sleep(delay)

        failed = ToolResult(
            ok=False,
            tool=self.spec.name,
            output={},
            sources=[],
            error=str(last_error) if last_error else "unknown tool failure",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        append_trace(failed.to_dict())
        return failed

    @abstractmethod
    def _run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    @staticmethod
    def make_source(
        *,
        url: str,
        source: str,
        snippet: str,
        confidence: float,
        retrieved_at: Optional[str] = None,
    ) -> SourceAttribution:
        return SourceAttribution(
            url=url,
            source=source,
            retrieved_at=retrieved_at
            or datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            snippet=snippet,
            confidence=max(0.0, min(confidence, 1.0)),
        )
