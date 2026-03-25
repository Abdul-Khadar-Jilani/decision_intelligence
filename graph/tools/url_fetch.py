from __future__ import annotations

from typing import Any, Dict
from urllib.request import Request, urlopen

from .base import BaseTool, RetryPolicy, ToolResult, ToolSpec


class URLFetchTool(BaseTool):
    spec = ToolSpec(
        name="url_fetch",
        description="Fetches page content from a URL and returns a short text snippet.",
        input_schema={"type": "object", "required": ["url"]},
        output_schema={
            "type": "object",
            "required": ["url", "content", "snippet", "retrieved_at", "confidence"],
        },
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.4),
    )

    def _run(self, **kwargs: Any) -> ToolResult:
        url = kwargs["url"]
        timeout = int(kwargs.get("timeout", 10))

        req = Request(url, headers={"User-Agent": "decision-intelligence-bot/0.1"})
        with urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="replace")

        snippet = " ".join(content.split())[:280]
        source = self.make_source(
            url=url,
            source="url_fetch",
            snippet=snippet,
            confidence=0.9,
        )

        output: Dict[str, Any] = {
            "url": url,
            "content": content,
            "snippet": source.snippet,
            "retrieved_at": source.retrieved_at,
            "confidence": source.confidence,
        }

        return ToolResult(
            ok=True,
            tool=self.spec.name,
            output=output,
            sources=[source],
            latency_ms=0,
        )


url_fetch = URLFetchTool()
