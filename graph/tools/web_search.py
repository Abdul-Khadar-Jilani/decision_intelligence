from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .base import BaseTool, RetryPolicy, ToolResult, ToolSpec


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._capture = False
        self._current_href = ""
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {k: v for k, v in attrs}
        class_name = attr_map.get("class", "") or ""
        if "result__a" in class_name and attr_map.get("href"):
            self._capture = True
            self._current_href = attr_map["href"] or ""
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture:
            title = " ".join("".join(self._text_parts).split())
            if title and self._current_href:
                self.results.append({"title": title, "url": self._current_href})
            self._capture = False
            self._current_href = ""
            self._text_parts = []


class WebSearchTool(BaseTool):
    spec = ToolSpec(
        name="web_search",
        description="Runs a web search and returns ranked links/snippets.",
        input_schema={"type": "object", "required": ["query"]},
        output_schema={
            "type": "object",
            "required": ["query", "results", "snippet", "retrieved_at", "confidence"],
        },
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.5),
    )

    def _run(self, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        limit = int(kwargs.get("limit", 5))
        endpoint = f"https://duckduckgo.com/html/?q={quote_plus(query)}"

        req = Request(endpoint, headers={"User-Agent": "decision-intelligence-bot/0.1"})
        with urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")

        parser = _DuckDuckGoParser()
        parser.feed(html)
        raw_results = parser.results[:limit]

        sources = []
        normalized_results: List[Dict[str, Any]] = []
        for idx, result in enumerate(raw_results):
            confidence = max(0.3, 0.85 - (idx * 0.08))
            source = self.make_source(
                url=result["url"],
                source="duckduckgo",
                snippet=result["title"][:220],
                confidence=confidence,
            )
            sources.append(source)
            normalized_results.append(
                {
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": source.snippet,
                    "retrieved_at": source.retrieved_at,
                    "confidence": source.confidence,
                }
            )

        top_snippet = normalized_results[0]["snippet"] if normalized_results else ""
        top_retrieved_at = (
            normalized_results[0]["retrieved_at"] if normalized_results else ""
        )
        top_confidence = normalized_results[0]["confidence"] if normalized_results else 0.0

        output: Dict[str, Any] = {
            "query": query,
            "results": normalized_results,
            "snippet": top_snippet,
            "retrieved_at": top_retrieved_at,
            "confidence": top_confidence,
            "url": normalized_results[0]["url"] if normalized_results else "",
            "source": "duckduckgo",
        }
        return ToolResult(
            ok=True,
            tool=self.spec.name,
            output=output,
            sources=sources,
            latency_ms=0,
        )


web_search = WebSearchTool()
