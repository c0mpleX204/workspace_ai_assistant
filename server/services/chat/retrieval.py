from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from server.config.config import settings
from server.dialogue.prompts import QUERY_REWRITE_SYSTEM_PROMPT
from server.infra.repo import list_chunks_emb, list_chunks_emb_multi
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


def retrieve_chunks_for_chat(
    query: str,
    document_id: Optional[int] = None,
    top_k: int = 3,
    candidate_limit: int = 500,
) -> List[Dict[str, object]]:
    q = query.strip()
    if not q:
        return []

    query_vec = embed_text(q)
    candidates = list_chunks_emb(document_id=document_id, limit=candidate_limit)
    if not candidates:
        return []
    ranked = rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)
    return ranked


def retrieve_chunks_multi(
    query: str,
    document_ids: List[int],
    top_k: int = 5,
    candidate_limit: int = 1000,
) -> List[Dict[str, object]]:
    if not document_ids or not query.strip():
        return []
    query_vec = embed_text(query.strip())
    candidates = list_chunks_emb_multi(document_ids=document_ids, limit=candidate_limit)
    if not candidates:
        return []
    return rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)
