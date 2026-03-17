"""
Tavily web search integration.
Returns top search result snippets as context for LLM prompts.
"""

import os
import requests


def tavily_search(query: str, max_results: int = 3) -> str:
    """
    Search the web via Tavily API and return formatted snippets.

    Args:
        query: Search query string
        max_results: Number of results to return

    Returns:
        Formatted string of search result snippets
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ""

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return ""

        snippets = []
        for i, result in enumerate(results[:max_results], 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")
            snippets.append(f"[{i}] {title}\n    URL: {url}\n    {content}")

        return "\n\n".join(snippets)

    except Exception as e:
        print(f"⚠ Tavily search failed: {e}")
        return ""
