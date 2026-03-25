from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Dict, List

from .base import BaseTool, RetryPolicy, ToolResult, ToolSpec
from .url_fetch import url_fetch


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._table: List[List[str]] = []
        self._row: List[str] = []
        self._cell_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._table = []
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._row = []
        elif tag in {"th", "td"} and self._in_row:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._in_cell:
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                self._table.append(self._row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._table:
                self.tables.append(self._table)
            self._in_table = False


class TableExtractorTool(BaseTool):
    spec = ToolSpec(
        name="table_extractor",
        description="Extracts HTML tables from a URL.",
        input_schema={"type": "object", "required": ["url"]},
        output_schema={
            "type": "object",
            "required": ["url", "tables", "snippet", "retrieved_at", "confidence"],
        },
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
    )

    def _run(self, **kwargs: Any) -> ToolResult:
        url = kwargs["url"]
        fetch_result = url_fetch.run(url=url)
        if not fetch_result.ok:
            return ToolResult(
                ok=False,
                tool=self.spec.name,
                output={},
                sources=[],
                error=fetch_result.error,
                latency_ms=0,
            )

        html = fetch_result.output.get("content", "")
        parser = _TableParser()
        parser.feed(html)

        snippet = f"Extracted {len(parser.tables)} table(s) from page"
        source = self.make_source(
            url=url,
            source="table_extractor",
            snippet=snippet,
            confidence=0.8 if parser.tables else 0.45,
        )

        output: Dict[str, Any] = {
            "url": url,
            "tables": parser.tables,
            "snippet": source.snippet,
            "retrieved_at": source.retrieved_at,
            "confidence": source.confidence,
            "source": source.source,
        }

        return ToolResult(
            ok=True,
            tool=self.spec.name,
            output=output,
            sources=[source],
            latency_ms=0,
        )


table_extractor = TableExtractorTool()
