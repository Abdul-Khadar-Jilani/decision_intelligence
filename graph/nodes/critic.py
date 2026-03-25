from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Iterable, Sequence


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class PlanDimension:
    name: str


@dataclass(slots=True)
class Claim:
    text: str
    source_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class SourceRecord:
    source_id: str
    published_at: date | datetime


@dataclass(slots=True)
class AgentFinding:
    agent_id: str
    dimension: str
    claims: tuple[Claim, ...] = ()
    confidence: float = 1.0
    stance: str = "neutral"


@dataclass(slots=True)
class RemediationTask:
    title: str
    description: str
    owner: str = "research"
    severity: Severity = Severity.MEDIUM


@dataclass(slots=True)
class CritiqueIssue:
    category: str
    severity: Severity
    summary: str
    affected_dimensions: tuple[str, ...] = ()
    affected_agents: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    remediation_tasks: tuple[RemediationTask, ...] = ()


@dataclass(slots=True)
class CritiqueReport:
    issues: tuple[CritiqueIssue, ...] = ()
    remediation_tasks: tuple[RemediationTask, ...] = ()
    should_reresearch: bool = False


@dataclass(slots=True)
class CriticConfig:
    stale_after_days: int = 180
    low_confidence_threshold: float = 0.55
    contradiction_stances: frozenset[str] = field(
        default_factory=lambda: frozenset({"supports", "refutes"})
    )


def _to_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _task(title: str, description: str, severity: Severity) -> RemediationTask:
    return RemediationTask(title=title, description=description, severity=severity)


def run_critic(
    plan_dimensions: Sequence[PlanDimension],
    findings: Sequence[AgentFinding],
    sources: Sequence[SourceRecord],
    *,
    config: CriticConfig | None = None,
    as_of: date | None = None,
) -> CritiqueReport:
    """Validate multi-agent research and emit actionable critique output."""
    config = config or CriticConfig()
    as_of = as_of or date.today()

    issues: list[CritiqueIssue] = []
    remediation_tasks: list[RemediationTask] = []

    issues.extend(_check_missing_dimensions(plan_dimensions, findings, remediation_tasks))
    issues.extend(_check_unsupported_claims(findings, remediation_tasks))
    issues.extend(_check_stale_sources(sources, config, as_of, remediation_tasks))
    issues.extend(
        _check_contradictory_findings(findings, config, remediation_tasks)
    )
    issues.extend(_check_low_confidence_clusters(findings, config, remediation_tasks))

    should_reresearch = any(
        issue.severity in {Severity.HIGH, Severity.CRITICAL} for issue in issues
    )

    return CritiqueReport(
        issues=tuple(issues),
        remediation_tasks=tuple(remediation_tasks),
        should_reresearch=should_reresearch,
    )


def _check_missing_dimensions(
    plan_dimensions: Sequence[PlanDimension],
    findings: Sequence[AgentFinding],
    remediation_tasks: list[RemediationTask],
) -> Iterable[CritiqueIssue]:
    planned = {dimension.name for dimension in plan_dimensions}
    covered = {finding.dimension for finding in findings}
    missing = tuple(sorted(planned - covered))
    if not missing:
        return []

    task = _task(
        title="Fill uncovered plan dimensions",
        description=(
            "Assign targeted follow-up queries for missing dimensions: "
            f"{', '.join(missing)}."
        ),
        severity=Severity.HIGH,
    )
    remediation_tasks.append(task)
    return [
        CritiqueIssue(
            category="missing_dimensions",
            severity=Severity.HIGH,
            summary="Required plan dimensions are missing from agent findings.",
            affected_dimensions=missing,
            remediation_tasks=(task,),
        )
    ]


def _check_unsupported_claims(
    findings: Sequence[AgentFinding],
    remediation_tasks: list[RemediationTask],
) -> Iterable[CritiqueIssue]:
    unsupported: list[tuple[str, str, str]] = []
    for finding in findings:
        for claim in finding.claims:
            if not claim.source_ids:
                unsupported.append((finding.agent_id, finding.dimension, claim.text))

    if not unsupported:
        return []

    task = _task(
        title="Backfill citations for unsupported claims",
        description="Collect primary sources for claims currently lacking evidence links.",
        severity=Severity.HIGH,
    )
    remediation_tasks.append(task)

    return [
        CritiqueIssue(
            category="unsupported_claims",
            severity=Severity.HIGH,
            summary="Some claims are not supported by any cited source.",
            affected_dimensions=tuple(sorted({item[1] for item in unsupported})),
            affected_agents=tuple(sorted({item[0] for item in unsupported})),
            evidence=tuple(item[2] for item in unsupported),
            remediation_tasks=(task,),
        )
    ]


def _check_stale_sources(
    sources: Sequence[SourceRecord],
    config: CriticConfig,
    as_of: date,
    remediation_tasks: list[RemediationTask],
) -> Iterable[CritiqueIssue]:
    stale_cutoff = as_of - timedelta(days=config.stale_after_days)
    stale_sources = [
        source for source in sources if _to_date(source.published_at) < stale_cutoff
    ]
    if not stale_sources:
        return []

    task = _task(
        title="Refresh stale evidence",
        description=(
            "Replace or re-validate stale references older than "
            f"{config.stale_after_days} days."
        ),
        severity=Severity.MEDIUM,
    )
    remediation_tasks.append(task)

    return [
        CritiqueIssue(
            category="stale_sources",
            severity=Severity.MEDIUM,
            summary="Some sources are stale and may no longer reflect current reality.",
            evidence=tuple(source.source_id for source in stale_sources),
            remediation_tasks=(task,),
        )
    ]


def _check_contradictory_findings(
    findings: Sequence[AgentFinding],
    config: CriticConfig,
    remediation_tasks: list[RemediationTask],
) -> Iterable[CritiqueIssue]:
    by_dimension: dict[str, set[str]] = {}
    dimension_agents: dict[str, set[str]] = {}
    for finding in findings:
        by_dimension.setdefault(finding.dimension, set()).add(finding.stance)
        dimension_agents.setdefault(finding.dimension, set()).add(finding.agent_id)

    contradictory = [
        dimension
        for dimension, stances in by_dimension.items()
        if config.contradiction_stances.issubset(stances)
    ]
    if not contradictory:
        return []

    task = _task(
        title="Resolve contradictory findings",
        description=(
            "Run targeted re-research and adjudication for dimensions with both "
            "supporting and refuting conclusions."
        ),
        severity=Severity.CRITICAL,
    )
    remediation_tasks.append(task)

    agents = tuple(
        sorted(
            {
                agent
                for dimension in contradictory
                for agent in dimension_agents.get(dimension, set())
            }
        )
    )

    return [
        CritiqueIssue(
            category="contradictory_findings",
            severity=Severity.CRITICAL,
            summary="Agents reported contradictory conclusions for the same dimension.",
            affected_dimensions=tuple(sorted(contradictory)),
            affected_agents=agents,
            remediation_tasks=(task,),
        )
    ]


def _check_low_confidence_clusters(
    findings: Sequence[AgentFinding],
    config: CriticConfig,
    remediation_tasks: list[RemediationTask],
) -> Iterable[CritiqueIssue]:
    if not findings:
        return []

    totals: dict[str, tuple[float, int]] = {}
    for finding in findings:
        score, count = totals.get(finding.dimension, (0.0, 0))
        totals[finding.dimension] = (score + finding.confidence, count + 1)

    low_dimensions = tuple(
        sorted(
            dimension
            for dimension, (score, count) in totals.items()
            if (score / count) < config.low_confidence_threshold
        )
    )

    if not low_dimensions:
        return []

    task = _task(
        title="Increase confidence for weak clusters",
        description=(
            "Gather additional high-quality sources and rerun analysis for low-confidence "
            f"dimensions: {', '.join(low_dimensions)}."
        ),
        severity=Severity.MEDIUM,
    )
    remediation_tasks.append(task)

    return [
        CritiqueIssue(
            category="low_confidence_clusters",
            severity=Severity.MEDIUM,
            summary="Confidence scores are below threshold for one or more dimensions.",
            affected_dimensions=low_dimensions,
            remediation_tasks=(task,),
        )
    ]
