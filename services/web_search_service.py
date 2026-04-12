import logging
from typing import Dict, List


def web_search(query: str, top_k: int = 5) -> List[Dict[str, str]]:
    """
    Web search using DuckDuckGo (free, no API key needed).
    Returns [{title, url, snippet}] list, empty list on failure.
    """
    try:
        from ddgs import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=top_k):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                )
        return results
    except ImportError:
        logging.warning("ddgs not installed. Run: pip install ddgs")
        return []
    except Exception as exc:
        logging.warning(f"web_search failed: {exc}")
        return []
