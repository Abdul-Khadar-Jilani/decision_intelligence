"""Output-quality evaluation node.

This module scores generated outputs across five quality dimensions and decides
where to route low-quality outputs for recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import UTC, datetime
import json
import sqlite3
from typing import Any


@dataclass(frozen=True)
class MetricThreshold:
    """Thresholds for one metric."""

    warn: float
    fail: float


@dataclass(frozen=True)
class EvaluatorThresholds:
    """Threshold bundle for all quality dimensions."""

    citation_completeness: MetricThreshold = MetricThreshold(warn=0.9, fail=0.75)
    claim_support_ratio: MetricThreshold = MetricThreshold(warn=0.85, fail=0.7)
    contradiction_count: MetricThreshold = MetricThreshold(warn=1.0, fail=3.0)
    plan_coverage: MetricThreshold = MetricThreshold(warn=0.85, fail=0.7)
    recency_quality: MetricThreshold = MetricThreshold(warn=0.8, fail=0.6)


@dataclass
class EvaluationResult:
    citation_completeness: float
    claim_support_ratio: float
    contradiction_count: int
    plan_coverage: float
    recency_quality: float
    status: str
    route: str
    reasons: list[str]


DEFAULT_THRESHOLDS = EvaluatorThresholds()


def _bounded_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, numerator / denominator))


def _compute_citation_completeness(payload: dict[str, Any]) -> float:
    total_claims = int(payload.get("claims_total", 0))
    claims_with_citations = int(payload.get("claims_with_citations", 0))
    return _bounded_ratio(claims_with_citations, total_claims)


def _compute_claim_support_ratio(payload: dict[str, Any]) -> float:
    supported_claims = int(payload.get("supported_claims", 0))
    total_claims = int(payload.get("claims_total", 0))
    return _bounded_ratio(supported_claims, total_claims)


def _compute_contradiction_count(payload: dict[str, Any]) -> int:
    return int(payload.get("contradiction_count", 0))


def _compute_plan_coverage(payload: dict[str, Any]) -> float:
    plan_items_total = int(payload.get("plan_items_total", 0))
    plan_items_addressed = int(payload.get("plan_items_addressed", 0))
    return _bounded_ratio(plan_items_addressed, plan_items_total)


def _compute_recency_quality(payload: dict[str, Any]) -> float:
    """Recency quality based on source freshness checks already done upstream.

    Expected payload keys:
    - recent_sources: Number of sources judged current enough.
    - total_sources: Number of sources used.
    """

    recent_sources = int(payload.get("recent_sources", 0))
    total_sources = int(payload.get("total_sources", 0))
    return _bounded_ratio(recent_sources, total_sources)


def _evaluate_against_threshold(value: float, threshold: MetricThreshold, *, lower_is_better: bool = False) -> str:
    """Return pass/warn/fail for one metric."""

    if lower_is_better:
        if value >= threshold.fail:
            return "fail"
        if value >= threshold.warn:
            return "warn"
        return "pass"

    if value <= threshold.fail:
        return "fail"
    if value <= threshold.warn:
        return "warn"
    return "pass"


def _decide_route(metric_states: dict[str, str], contradiction_count: int) -> tuple[str, list[str], str]:
    """Route low-quality output back to planner or specific research nodes."""

    reasons: list[str] = []

    if metric_states["plan_coverage"] == "fail":
        reasons.append("plan coverage failed")
        return "planner", reasons, "fail"

    if contradiction_count >= int(DEFAULT_THRESHOLDS.contradiction_count.fail):
        reasons.append("too many contradictions")
        return "research.fact_check", reasons, "fail"

    if metric_states["citation_completeness"] == "fail":
        reasons.append("missing citations")
        return "research.citations", reasons, "fail"

    if metric_states["claim_support_ratio"] == "fail":
        reasons.append("claims unsupported")
        return "research.evidence", reasons, "fail"

    if metric_states["recency_quality"] == "fail":
        reasons.append("stale sources")
        return "research.recency", reasons, "fail"

    warnings = [name for name, state in metric_states.items() if state == "warn"]
    if warnings:
        reasons.extend(f"{metric} warning" for metric in warnings)
        if "plan_coverage" in warnings:
            return "planner", reasons, "warn"
        if "recency_quality" in warnings:
            return "research.recency", reasons, "warn"
        if "citation_completeness" in warnings:
            return "research.citations", reasons, "warn"
        if "claim_support_ratio" in warnings or "contradiction_count" in warnings:
            return "research.evidence", reasons, "warn"

    return "respond", reasons, "pass"


def ensure_evaluations_table(connection: sqlite3.Connection) -> None:
    """Create the evaluations table used for benchmarking history."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            citation_completeness REAL NOT NULL,
            claim_support_ratio REAL NOT NULL,
            contradiction_count INTEGER NOT NULL,
            plan_coverage REAL NOT NULL,
            recency_quality REAL NOT NULL,
            status TEXT NOT NULL,
            route TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.commit()


def persist_evaluation(connection: sqlite3.Connection, run_id: str, result: EvaluationResult, payload: dict[str, Any]) -> None:
    """Persist one evaluation record for later benchmarking."""

    ensure_evaluations_table(connection)
    connection.execute(
        """
        INSERT INTO evaluations (
            run_id,
            created_at,
            citation_completeness,
            claim_support_ratio,
            contradiction_count,
            plan_coverage,
            recency_quality,
            status,
            route,
            reasons_json,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            datetime.now(UTC).isoformat(),
            result.citation_completeness,
            result.claim_support_ratio,
            result.contradiction_count,
            result.plan_coverage,
            result.recency_quality,
            result.status,
            result.route,
            json.dumps(result.reasons),
            json.dumps(payload),
        ),
    )
    connection.commit()


def evaluate_output(payload: dict[str, Any], *, run_id: str, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Compute quality metrics, determine routing, and optionally persist history.

    Payload structure is intentionally simple to keep this node composable with
    upstream graph nodes.
    """

    citation_completeness = _compute_citation_completeness(payload)
    claim_support_ratio = _compute_claim_support_ratio(payload)
    contradiction_count = _compute_contradiction_count(payload)
    plan_coverage = _compute_plan_coverage(payload)
    recency_quality = _compute_recency_quality(payload)

    metric_states = {
        "citation_completeness": _evaluate_against_threshold(
            citation_completeness,
            DEFAULT_THRESHOLDS.citation_completeness,
        ),
        "claim_support_ratio": _evaluate_against_threshold(
            claim_support_ratio,
            DEFAULT_THRESHOLDS.claim_support_ratio,
        ),
        "contradiction_count": _evaluate_against_threshold(
            float(contradiction_count),
            DEFAULT_THRESHOLDS.contradiction_count,
            lower_is_better=True,
        ),
        "plan_coverage": _evaluate_against_threshold(
            plan_coverage,
            DEFAULT_THRESHOLDS.plan_coverage,
        ),
        "recency_quality": _evaluate_against_threshold(
            recency_quality,
            DEFAULT_THRESHOLDS.recency_quality,
        ),
    }

    route, reasons, status = _decide_route(metric_states, contradiction_count)

    result = EvaluationResult(
        citation_completeness=citation_completeness,
        claim_support_ratio=claim_support_ratio,
        contradiction_count=contradiction_count,
        plan_coverage=plan_coverage,
        recency_quality=recency_quality,
        status=status,
        route=route,
        reasons=reasons,
    )

    if connection is not None:
        persist_evaluation(connection, run_id, result, payload)

    response = asdict(result)
    response["metric_states"] = metric_states
    return response
