from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from server.config.config import settings
from server.dialogue.prompts import QUERY_REWRITE_SYSTEM_PROMPT
from server.infra.repo import list_chunks_emb, list_chunks_emb_multi, list_chunks_text
from server.services.ai.embedding import embed_text, rank_chunks
from server.services.ai.model import smart_model_dispatch

def get_latest_user_query(messages: List[Dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", "")).strip()
    return ""


AUTO_WEB_PATTERNS = (
    r"联网|上网|网上|网页|搜索|搜一下|查一下|查找|查资料|实时|最新|新闻|今天|昨日|昨天|明天|现在|当前|近期",
    r"价格|股价|汇率|天气|赛程|比分|版本|发布|政策|法规|招聘|官网|链接|url",
    r"web|internet|online|search|look up|latest|current|today|news|price|weather|release|docs?",
)


def should_auto_web_search(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    text = re.split(r"\n\s*<(?:file|selection)\b", text, maxsplit=1)[0].strip() or text
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in AUTO_WEB_PATTERNS)


def rewrite_retrieval_query(raw_query: str, messages: List[Dict[str, str]]) -> str:
    query = str(raw_query or "").strip()
    if not query:
        return ""
    recent = [
        {
            "role": str(m.get("role", "")),
            "content": str(m.get("content", "")).strip()[:500],
        }
        for m in messages[-6:]
        if str(m.get("role", "")) in {"user", "assistant"} and str(m.get("content", "")).strip()
    ]
    if len(query) < 12 and len(recent) <= 1:
        return query

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": QUERY_REWRITE_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"最近对话：\n{json.dumps(recent, ensure_ascii=False)}\n\n"
                            f"用户原始输入：{query}\n\n"
                            "改写查询："
                        ),
                    },
                ],
                "model": settings.remote_fast_model,
                "generation": {
                    "max_tokens": 120,
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
            }
        )
        rewritten = str(result.get("reply", "")).strip()
        rewritten = re.sub(r"^改写查询[:：]\s*", "", rewritten).strip().strip('"')
        if rewritten and len(rewritten) <= 240:
            return rewritten
    except Exception as exc:
        logging.warning("rewrite retrieval query failed: %s", exc)
    return query


def _lexical_tokens(text: str) -> List[str]:
    raw = str(text or "").lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", raw)
    return [token for token in tokens if token.strip()]


def _rank_chunks_by_text(query: str, chunks: List[Dict[str, object]], top_k: int) -> List[Dict[str, object]]:
    tokens = list(dict.fromkeys(_lexical_tokens(query)))
    if not tokens:
        return []
    scored: List[Dict[str, object]] = []
    query_text = str(query or "").strip().lower()
    for chunk in chunks:
        content = str(chunk.get("content") or "")
        content_lower = content.lower()
        hits = sum(content_lower.count(token) for token in tokens)
        if query_text and query_text in content_lower:
            hits += max(5, len(tokens))
        if hits <= 0:
            continue
        scored.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "content": content,
                "score": float(hits),
                "document_id": chunk.get("document_id"),
                "document_title": chunk.get("document_title"),
                "page_no": chunk.get("page_no"),
                "source_path": chunk.get("source_path"),
            }
        )
    scored.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return scored[:top_k]


def retrieve_chunks_for_chat(
    query: str,
    document_id: Optional[int] = None,
    top_k: int = 3,
    candidate_limit: int = 500,
) -> List[Dict[str, object]]:
    q = query.strip()
    if not q:
        return []

    try:
        query_vec = embed_text(q)
        candidates = list_chunks_emb(document_id=document_id, limit=candidate_limit)
        if candidates:
            return rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)
    except Exception as exc:
        logging.warning("embedding retrieval failed; falling back to parsed text: %s", exc)

    parsed_chunks = list_chunks_text(document_id=document_id, limit=candidate_limit)
    return _rank_chunks_by_text(q, parsed_chunks, top_k=top_k)


def retrieve_chunks_multi(
    query: str,
    document_ids: List[int],
    top_k: int = 5,
    candidate_limit: int = 1000,
) -> List[Dict[str, object]]:
    if not document_ids or not query.strip():
        return []
    q = query.strip()
    try:
        query_vec = embed_text(q)
        candidates = list_chunks_emb_multi(document_ids=document_ids, limit=candidate_limit)
        if candidates:
            return rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)
    except Exception as exc:
        logging.warning("multi embedding retrieval failed; falling back to parsed text: %s", exc)

    parsed_chunks = list_chunks_text(document_ids=document_ids, limit=candidate_limit)
    return _rank_chunks_by_text(q, parsed_chunks, top_k=top_k)
