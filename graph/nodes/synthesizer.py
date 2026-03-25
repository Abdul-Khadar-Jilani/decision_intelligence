"""Synthesis node output rendering.

This module supports structured output formats and enforces:
- claim-level citations sourced from evidence_db claim mapping
- confidence bands for major claims
- a known unknowns section in every output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

SUPPORTED_OUTPUT_FORMATS = {
    "executive memo",
    "comparison matrix",
    "slide deck outline",
}


@dataclass(frozen=True)
class SourceRef:
    """Canonical reference to a source for a claim."""

    source_id: str
    title: str | None = None
    url: str | None = None

    def render(self) -> str:
        if self.title and self.url:
            return f"{self.source_id} ({self.title}: {self.url})"
        if self.title:
            return f"{self.source_id} ({self.title})"
        if self.url:
            return f"{self.source_id} ({self.url})"
        return self.source_id


@dataclass
class MajorClaim:
    """Represents a synthesized major claim."""

    text: str
    confidence_band: str


@dataclass
class SynthesisPayload:
    """Input payload for synthesis rendering."""

    title: str
    objective: str
    major_claims: list[MajorClaim]
    comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    slides: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    known_unknowns: list[str] = field(default_factory=list)


class Synthesizer:
    """Render synthesis outputs with citations, confidence, and known unknowns."""

    def render(
        self,
        payload: SynthesisPayload,
        output_format: str,
        evidence_db: dict[str, Iterable[SourceRef | dict[str, Any] | str]],
    ) -> str:
        output_format = output_format.strip().lower()
        self._validate_output_format(output_format)
        citation_map = self._build_claim_to_source_map(payload.major_claims, evidence_db)

        if output_format == "executive memo":
            return self._render_executive_memo(payload, citation_map)
        if output_format == "comparison matrix":
            return self._render_comparison_matrix(payload, citation_map)
        return self._render_slide_deck_outline(payload, citation_map)

    def _validate_output_format(self, output_format: str) -> None:
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            supported = ", ".join(sorted(SUPPORTED_OUTPUT_FORMATS))
            raise ValueError(f"Unsupported output format '{output_format}'. Supported: {supported}")

    def _build_claim_to_source_map(
        self,
        major_claims: list[MajorClaim],
        evidence_db: dict[str, Iterable[SourceRef | dict[str, Any] | str]],
    ) -> dict[str, list[SourceRef]]:
        claim_map: dict[str, list[SourceRef]] = {}
        for claim in major_claims:
            mapped_sources = list(evidence_db.get(claim.text, []))
            if not mapped_sources:
                raise ValueError(f"Missing required citations in evidence_db for major claim: {claim.text}")
            claim_map[claim.text] = [self._normalize_source_ref(source) for source in mapped_sources]
        return claim_map

    def _normalize_source_ref(self, source: SourceRef | dict[str, Any] | str) -> SourceRef:
        if isinstance(source, SourceRef):
            return source
        if isinstance(source, str):
            return SourceRef(source_id=source)
        if isinstance(source, dict):
            if "source_id" not in source:
                raise ValueError("Source dict must include 'source_id'")
            return SourceRef(
                source_id=str(source["source_id"]),
                title=str(source.get("title")) if source.get("title") else None,
                url=str(source.get("url")) if source.get("url") else None,
            )
        raise TypeError(f"Unsupported source type: {type(source)!r}")

    def _render_claims_with_citations(
        self,
        claims: list[MajorClaim],
        citation_map: dict[str, list[SourceRef]],
    ) -> list[str]:
        rendered = []
        for idx, claim in enumerate(claims, start=1):
            refs = "; ".join(ref.render() for ref in citation_map[claim.text])
            rendered.append(
                f"{idx}. {claim.text}\n"
                f"   - Confidence band: {claim.confidence_band}\n"
                f"   - Citations: {refs}"
            )
        return rendered

    def _render_known_unknowns(self, known_unknowns: list[str]) -> str:
        if not known_unknowns:
            return "## Known Unknowns\n- None explicitly identified."
        lines = "\n".join(f"- {item}" for item in known_unknowns)
        return f"## Known Unknowns\n{lines}"

    def _render_executive_memo(
        self,
        payload: SynthesisPayload,
        citation_map: dict[str, list[SourceRef]],
    ) -> str:
        claims = "\n".join(self._render_claims_with_citations(payload.major_claims, citation_map))
        recs = "\n".join(f"- {item}" for item in payload.recommendations) or "- No recommendations provided."
        return (
            f"# Executive Memo: {payload.title}\n\n"
            f"## Objective\n{payload.objective}\n\n"
            f"## Major Claims\n{claims}\n\n"
            f"## Recommendations\n{recs}\n\n"
            f"{self._render_known_unknowns(payload.known_unknowns)}"
        )

    def _render_comparison_matrix(
        self,
        payload: SynthesisPayload,
        citation_map: dict[str, list[SourceRef]],
    ) -> str:
        headers = ["Option", "Pros", "Cons", "Evidence"]
        matrix_lines = ["| " + " | ".join(headers) + " |", "|---|---|---|---|"]
        for row in payload.comparison_rows:
            matrix_lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("option", "")),
                        str(row.get("pros", "")),
                        str(row.get("cons", "")),
                        str(row.get("evidence", "")),
                    ]
                )
                + " |"
            )

        claims = "\n".join(self._render_claims_with_citations(payload.major_claims, citation_map))
        matrix = "\n".join(matrix_lines)
        return (
            f"# Comparison Matrix: {payload.title}\n\n"
            f"## Decision Objective\n{payload.objective}\n\n"
            f"{matrix}\n\n"
            f"## Major Claims\n{claims}\n\n"
            f"{self._render_known_unknowns(payload.known_unknowns)}"
        )

    def _render_slide_deck_outline(
        self,
        payload: SynthesisPayload,
        citation_map: dict[str, list[SourceRef]],
    ) -> str:
        slides = payload.slides or [
            "Title and objective",
            "Key findings",
            "Recommendation",
            "Risks and mitigation",
            "Known unknowns",
        ]
        slide_lines = "\n".join(f"{idx}. {slide}" for idx, slide in enumerate(slides, start=1))
        claims = "\n".join(self._render_claims_with_citations(payload.major_claims, citation_map))
        return (
            f"# Slide Deck Outline: {payload.title}\n\n"
            f"## Audience Objective\n{payload.objective}\n\n"
            f"## Proposed Slides\n{slide_lines}\n\n"
            f"## Claims, Confidence, and Citations\n{claims}\n\n"
            f"{self._render_known_unknowns(payload.known_unknowns)}"
        )
