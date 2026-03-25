from __future__ import annotations

from typing import Any

from .base import BaseTool, RetryPolicy, ToolResult, ToolSpec
from .web_search import web_search


class NewsLookupTool(BaseTool):
    spec = ToolSpec(
        name="news_lookup",
        description="Looks up news-like results using web search with recency intent.",
        input_schema={"type": "object", "required": ["query"]},
        output_schema={
            "type": "object",
            "required": ["query", "results", "snippet", "retrieved_at", "confidence"],
        },
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.4),
    )

    def _run(self, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        limit = int(kwargs.get("limit", 5))
        result = web_search.run(query=f"{query} latest news", limit=limit)

        if not result.ok:
            return ToolResult(
                ok=False,
                tool=self.spec.name,
                output={},
                sources=[],
                error=result.error,
                latency_ms=0,
            )

        output = {
            **result.output,
            "query": query,
            "source": "news_lookup",
            "url": result.output.get("url", ""),
            "snippet": result.output.get("snippet", ""),
            "retrieved_at": result.output.get("retrieved_at", ""),
            "confidence": min(1.0, result.output.get("confidence", 0.0) * 0.95),
        }
        return ToolResult(
            ok=True,
            tool=self.spec.name,
            output=output,
            sources=result.sources,
            latency_ms=0,
        )


news_lookup = NewsLookupTool()
