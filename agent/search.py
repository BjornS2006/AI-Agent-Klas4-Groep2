from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

SEARCH_TIMEOUT_SECONDS = float(os.getenv("SEARXNG_TIMEOUT", "10"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARXNG_MAX_RESULTS", "5"))


def get_searxng_base_url() -> str:
    return os.getenv("SEARXNG_BASE_URL", "http://localhost:8080").rstrip("/")


def _normalize_result(result: dict) -> dict:
    return {
        "title": result.get("title") or result.get("url") or "Onbekend resultaat",
        "url": result.get("url") or "",
        "snippet": result.get("content") or result.get("snippet") or "",
        "engine": result.get("engine") or "",
    }


def search_searxng(query: str, max_results: int = SEARCH_MAX_RESULTS) -> list[dict]:
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    params = urllib.parse.urlencode(
        {
            "q": cleaned_query,
            "format": "json",
            "pageno": 1,
        }
    )
    request_url = f"{get_searxng_base_url()}/search?{params}"
    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [
            {
                "title": "SearxNG fout",
                "url": "",
                "snippet": str(exc),
                "engine": "error",
            }
        ]

    if not isinstance(payload, dict):
        return []

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []

    return [
        _normalize_result(result)
        for result in raw_results[:max_results]
        if isinstance(result, dict)
    ]


def format_searxng_results(query: str, results: list[dict]) -> str:
    if not results:
        return ""

    lines = [f"Zoekresultaten voor: {query}"]
    for index, result in enumerate(results, start=1):
        parts = [f"{index}. {result.get('title', 'Onbekend resultaat')}"]
        url = result.get("url", "")
        engine = result.get("engine", "")
        snippet = result.get("snippet", "")
        if url:
            parts.append(f"URL: {url}")
        if engine:
            parts.append(f"Bron: {engine}")
        if snippet:
            parts.append(f"Snippet: {snippet}")
        lines.append(" | ".join(parts))

    return "\n".join(lines)