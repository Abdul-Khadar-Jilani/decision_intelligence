"""Policy-based LLM model router.

This module provides:
- Task policy selection via ``select_model(task_type, complexity, latency_budget)``
- Route decision auditing in ``execution_log``
- Graceful fallback chains across providers/models
- Structured error handling for provider failures and timeouts
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Callable


class TaskType(str, Enum):
    """Canonical task categories for model routing."""

    INTENT_CLASSIFICATION = "intent_classification"
    TOOL_ROUTING = "tool_routing"
    PLANNING = "planning"
    CRITIQUE = "critique"
    SYNTHESIS = "synthesis"
    BACKGROUND = "background"
    GENERAL = "general"


class Complexity(str, Enum):
    """Relative complexity used as a route hint."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyBudget(str, Enum):
    """Latency sensitivity for route decisions."""

    TIGHT = "tight"
    NORMAL = "normal"
    RELAXED = "relaxed"


@dataclass(frozen=True)
class ModelSpec:
    """Resolved model target used for a call attempt."""

    name: str
    provider: str
    tier: str


@dataclass(frozen=True)
class RoutePlan:
    """Primary route and fallback chain for a task."""

    primary: ModelSpec
    fallbacks: tuple[ModelSpec, ...]

    def chain(self) -> tuple[ModelSpec, ...]:
        return (self.primary, *self.fallbacks)


@dataclass
class RouteDecision:
    """Serializable route decision payload appended to execution_log."""

    timestamp: str
    task_type: str
    complexity: str
    latency_budget: str
    selected: dict[str, str]
    fallback_chain: list[dict[str, str]]
    reason: str


class RouterError(RuntimeError):
    """Base exception for routing execution failures."""


class ProviderTimeoutError(RouterError):
    """Provider timed out."""


class ProviderCallError(RouterError):
    """Provider call failed."""


class FallbackExhaustedError(RouterError):
    """All models in the fallback chain failed."""

    def __init__(self, message: str, errors: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.errors = errors


ProviderCallable = Callable[[str, list[dict[str, Any]], float | None], Any]


class ModelRouter:
    """Policy-based model router with fallbacks and decision logging."""

    def __init__(
        self,
        providers: dict[str, ProviderCallable] | None = None,
        *,
        local_model_enabled: bool = False,
    ) -> None:
        self.providers: dict[str, ProviderCallable] = providers or {}
        self.local_model_enabled = local_model_enabled
        self.execution_log: list[dict[str, Any]] = []

        self.lightweight_model = ModelSpec(
            name="gpt-4.1-mini",
            provider="openai",
            tier="lightweight",
        )
        self.reasoning_model = ModelSpec(
            name="gpt-5",
            provider="openai",
            tier="reasoning",
        )
        self.local_background_model = ModelSpec(
            name="llama3.1:8b-instruct",
            provider="local",
            tier="background_local",
        )
        self.safe_fallback_model = ModelSpec(
            name="gpt-4.1",
            provider="openai",
            tier="fallback",
        )

    def select_model(
        self,
        task_type: str,
        complexity: str,
        latency_budget: str,
    ) -> RoutePlan:
        """Select primary and fallback models from routing policy."""
        normalized_task = TaskType(task_type)
        normalized_complexity = Complexity(complexity)
        normalized_latency = LatencyBudget(latency_budget)

        if normalized_task in {TaskType.INTENT_CLASSIFICATION, TaskType.TOOL_ROUTING}:
            primary = self.lightweight_model
            reason = "Fast path for classification/tool selection."
        elif normalized_task in {TaskType.PLANNING, TaskType.CRITIQUE, TaskType.SYNTHESIS}:
            primary = self.reasoning_model
            reason = "Reasoning-intensive workflow task."
        elif normalized_task is TaskType.BACKGROUND and self.local_model_enabled:
            primary = self.local_background_model
            reason = "Low-priority background task routed to optional local model."
        else:
            if normalized_complexity is Complexity.HIGH:
                primary = self.reasoning_model
                reason = "High complexity task defaults to reasoning model."
            elif normalized_latency is LatencyBudget.TIGHT:
                primary = self.lightweight_model
                reason = "Tight latency budget favors lightweight model."
            else:
                primary = self.safe_fallback_model
                reason = "Balanced default route."

        fallback_chain = self._build_fallback_chain(primary)
        self._log_decision(
            task_type=normalized_task.value,
            complexity=normalized_complexity.value,
            latency_budget=normalized_latency.value,
            primary=primary,
            fallbacks=fallback_chain,
            reason=reason,
        )
        return RoutePlan(primary=primary, fallbacks=fallback_chain)

    def route_request(
        self,
        *,
        task_type: str,
        complexity: str,
        latency_budget: str,
        prompt: str,
        messages: list[dict[str, Any]] | None = None,
        timeout_s: float | None = None,
    ) -> Any:
        """Execute a model request using policy routing and failover."""
        plan = self.select_model(task_type, complexity, latency_budget)
        payload = messages or [{"role": "user", "content": prompt}]

        errors: list[dict[str, Any]] = []
        for model in plan.chain():
            started = time.perf_counter()
            provider_fn = self.providers.get(model.provider)
            if provider_fn is None:
                errors.append(
                    {
                        "model": model.name,
                        "provider": model.provider,
                        "error_type": "provider_unavailable",
                        "message": "No provider callable registered.",
                    }
                )
                continue

            try:
                result = provider_fn(model.name, payload, timeout_s)
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                self.execution_log.append(
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "execution_success",
                        "model": model.name,
                        "provider": model.provider,
                        "duration_ms": duration_ms,
                    }
                )
                return result
            except TimeoutError as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                errors.append(
                    {
                        "model": model.name,
                        "provider": model.provider,
                        "error_type": "timeout",
                        "duration_ms": duration_ms,
                        "message": str(exc),
                    }
                )
                self.execution_log.append(
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "execution_failure",
                        "model": model.name,
                        "provider": model.provider,
                        "duration_ms": duration_ms,
                        "error_type": "timeout",
                        "message": str(exc),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - preserve structured provider errors
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                errors.append(
                    {
                        "model": model.name,
                        "provider": model.provider,
                        "error_type": "provider_error",
                        "duration_ms": duration_ms,
                        "message": str(exc),
                    }
                )
                self.execution_log.append(
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "execution_failure",
                        "model": model.name,
                        "provider": model.provider,
                        "duration_ms": duration_ms,
                        "error_type": "provider_error",
                        "message": str(exc),
                    }
                )

        raise FallbackExhaustedError(
            "All model providers failed during fallback execution.",
            errors=errors,
        )

    def _build_fallback_chain(self, primary: ModelSpec) -> tuple[ModelSpec, ...]:
        ordered = [self.reasoning_model, self.safe_fallback_model, self.lightweight_model]
        if self.local_model_enabled:
            ordered.append(self.local_background_model)

        seen = {primary.name}
        chain: list[ModelSpec] = []
        for candidate in ordered:
            if candidate.name in seen:
                continue
            chain.append(candidate)
            seen.add(candidate.name)
        return tuple(chain)

    def _log_decision(
        self,
        *,
        task_type: str,
        complexity: str,
        latency_budget: str,
        primary: ModelSpec,
        fallbacks: tuple[ModelSpec, ...],
        reason: str,
    ) -> None:
        decision = RouteDecision(
            timestamp=_utc_now_iso(),
            task_type=task_type,
            complexity=complexity,
            latency_budget=latency_budget,
            selected=_serialize_model(primary),
            fallback_chain=[_serialize_model(model) for model in fallbacks],
            reason=reason,
        )
        self.execution_log.append(
            {
                "event": "route_decision",
                **decision.__dict__,
            }
        )


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _serialize_model(model: ModelSpec) -> dict[str, str]:
    return {
        "name": model.name,
        "provider": model.provider,
        "tier": model.tier,
    }


_default_router = ModelRouter()


def select_model(task_type: str, complexity: str, latency_budget: str) -> RoutePlan:
    """Module-level convenience API requested by orchestration code."""
    return _default_router.select_model(task_type, complexity, latency_budget)
