import asyncio
from datetime import datetime, timedelta
from html import escape
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional

import dateparser
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from config.config import settings
from memory.memory_rules import RULES, normalize_pref_signal
from infra.repo import (
    get_document_detail,
    list_chunks_with_embedding,
    list_chunks_with_embedding_multi,
    list_learning_progress,
    list_user_preferences,
    list_user_reminders,
    upsert_learning_progress,
    upsert_user_preference,
)
from services.embedding_service import cosine_similarity, embed_text, rank_chunks
from services.model_service import remote_stream_reply, smart_model_dispatch
from services.web_search_service import web_search

SESSION_STORE: Dict[str, List[Dict[str, str]]] = {}
LOG_HTML_PATH = Path("logs/error_logs.html")
LOG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)


def ensure_log_html_exists() -> None:
    if LOG_HTML_PATH.exists():
        return
    LOG_HTML_PATH.write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>Error Log</title>
<style>
body { font-family: Arial, sans-serif; margin: 24px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
tr:nth-child(even) { background: #fafafa; }
</style>
</head>
<body>
<h2>AI Assistant Error Log</h2>
<table>
<thead>
<tr>
<th>时间</th>
<th>会话ID</th>
<th>耗时(ms)</th>
<th>错误类型</th>
<th>错误详情</th>
</tr>
</thead>
<tbody>
</tbody>
</table>
</body>
</html>
""",
        encoding="utf-8",
    )


def append_error_row(session_id: str, latency_ms: int, error_type: str, detail: str) -> None:
    ensure_log_html_exists()
    html_text = LOG_HTML_PATH.read_text(encoding="utf-8")

    row = (
        "<tr>"
        f"<td>{escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</td>"
        f"<td>{escape(session_id)}</td>"
        f"<td>{latency_ms}</td>"
        f"<td>{escape(error_type)}</td>"
        f"<td>{escape(detail)}</td>"
        "</tr>"
    )

    marker = "</tbody>"
    if marker in html_text:
        html_text = html_text.replace(marker, row + marker, 1)
        LOG_HTML_PATH.write_text(html_text, encoding="utf-8")


def inject_system_prompt(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    persona = {"role": "system", "content": settings.persona_system_prompt}
    filtered = [
        m
        for m in messages
        if not (m.get("role") == "system" and m.get("content") == settings.persona_system_prompt)
    ]
    return [persona] + filtered


def get_short_term_memory(
    session_id: str,
    merged_messages: List[Dict[str, str]],
    rounds: int,
) -> Dict[str, object]:
    max_messages = max(2, rounds * 2)
    msgs = merged_messages[-max_messages:]
    return {
        "session_id": session_id,
        "window_rounds": rounds,
        "messages": [{"role": m.get("role", ""), "content": m.get("content", "")} for m in msgs],
    }


def build_memory_context_text(
    short_mem: Dict[str, object],
    pref_items: List[Dict[str, object]],
    progress_items: List[Dict[str, object]],
    pref_top_k: int,
    progress_top_k: int,
) -> str:
    lines: List[str] = []
    if pref_items:
        lines.append("【长期偏好】")
        for x in pref_items[:pref_top_k]:
            lines.append(f"-{x.get('key')}:{x.get('value')}")
    if progress_items:
        lines.append("【学习进度】")
        for x in progress_items[:progress_top_k]:
            nr = x.get("next_review_at")
            nr_text = f" / 到期 {nr}" if nr else ""
            lines.append(
                f"- 课程{x.get('course_id')} / {x.get('topic')} / 状态{x.get('status')} / 掌握度{x.get('mastery')}{nr_text}"
            )
    if short_mem.get("messages"):
        lines.append("【短期上下文】")
        for m in short_mem["messages"][-4:]:
            role = m.get("role", "")
            content = m.get("content", "").strip().replace("\n", " ")
            lines.append(f"- {role}: {content[:80]}")
    return "\n".join(lines).strip()


def extract_memory_signals(user_text: str, document_id: Optional[int]) -> tuple[list[dict], list[dict]]:
    text_raw = (user_text or "").strip()
    text = text_raw.lower()
    pref_signals: list[dict] = []
    progress_signals: list[dict] = []
    hit_rules = 0

    for rule in RULES:
        matched = False
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                matched = True
                break
        if not matched and rule.get("regex"):
            m = re.search(rule["regex"], text, re.I)
            if m:
                matched = True
        if not matched:
            continue

        hit_rules += 1
        if rule["type"] == "preference":
            val = rule.get("value")
            if rule.get("regex"):
                m = re.search(rule["regex"], text_raw, re.I)
                if m:
                    g = m.group(1) if m.groups() else m.group(0)
                    if rule.get("map"):
                        val = rule["map"].get(g, g)
                    else:
                        val = g
            raw_signal = {
                "key": rule["key"],
                "value": val,
                "source": "rule:",
                "confidence": rule.get("confidence", 0.5),
                "rule_id": rule.get("id"),
            }
            pref_signals.append(normalize_pref_signal(raw_signal))
        elif rule["type"] == "progress":
            next_review = None
            try:
                m = re.search(
                    r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)|(\d{1,2}月\d{1,2}日)|(\d{1,2}[/-]\d{1,2})",
                    text_raw,
                )
                date_candidate = m.group(0) if m else None
                if date_candidate:
                    dt = dateparser.parse(
                        date_candidate,
                        languages=["zh"],
                        settings={"PREFER_DATES_FROM": "future"},
                    )
                    if dt is None:
                        if re.match(r"^\d{1,2}[/-]\d{1,2}$", date_candidate):
                            parts = re.split(r"[/-]", date_candidate)
                            cand = f"{int(parts[0])}月{int(parts[1])}日"
                        else:
                            cand = date_candidate
                        year = datetime.utcnow().year
                        cand_with_year = f"{year}年{cand}"
                        dt = dateparser.parse(
                            cand_with_year,
                            languages=["zh"],
                            settings={"PREFER_DATES_FROM": "future"},
                        )
                else:
                    dt = dateparser.parse(
                        text_raw,
                        languages=["zh"],
                        settings={"PREFER_DATES_FROM": "future"},
                    )
                if dt:
                    next_review = dt.isoformat()
            except Exception:
                next_review = None

            progress_signals.append(
                {
                    "course_id": document_id or 0,
                    "topic": rule.get("topic"),
                    "status": rule.get("status"),
                    "mastery": rule.get("mastery"),
                    "evidence": text[:120],
                    "rule_id": rule.get("id"),
                    "next_review_at": next_review,
                }
            )

    logging.info(
        {
            "memory_rule_hits": hit_rules,
            "pref_signals": len(pref_signals),
            "progress_signals": len(progress_signals),
        }
    )
    return pref_signals, progress_signals


def persist_memory_signals(
    user_id: str,
    pref_signals: list[dict],
    progress_signals: list[dict],
) -> None:
    now = datetime.utcnow()
    short_write_window = timedelta(minutes=1)
    throttle_window = timedelta(hours=1)
    pref_hit = len(pref_signals)
    prog_hit = len(progress_signals)

    pref_written = 0
    pref_skipped = 0
    pref_failed = 0

    prog_written = 0
    prog_skipped = 0
    prog_failed = 0

    try:
        existing_prefs = list_user_preferences(user_id=user_id, limit=500)
    except Exception as exc:
        logging.warning(f"list_user_preferences failed: {exc}")
        existing_prefs = []

    def parse_time(t):
        if not t:
            return None
        if isinstance(t, datetime):
            return t
        try:
            return datetime.fromisoformat(str(t))
        except Exception:
            try:
                return datetime.strptime(str(t), "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    for s in pref_signals:
        try:
            key = str(s["key"])
            value = str(s["value"])
            source = str(s.get("source", "rule"))
            confidence = float(s.get("confidence")) if s.get("confidence") is not None else None
            recently_same = False
            for p in existing_prefs:
                if p.get("key") == key:
                    recently_same = p
                    break

            if recently_same:
                t = parse_time(recently_same.get("updated_at") or recently_same.get("last_seen"))
                if t and (now - t) <= short_write_window:
                    pref_skipped += 1
                    continue

            ok = upsert_user_preference(
                user_id=user_id,
                key=key,
                value=value,
                source=source,
                confidence=confidence,
            )
            if ok:
                pref_written += 1
            else:
                pref_failed += 1
        except Exception as exc:
            pref_failed += 1
            logging.warning(f"persist user preference failed: {exc}")

    try:
        existing_progress = list_learning_progress(user_id=user_id, limit=200)
    except Exception as exc:
        logging.warning(f"list_learning_progress failed: {exc}")
        existing_progress = []

    for s in progress_signals:
        try:
            course_id = s.get("course_id")
            topic = str(s.get("topic", ""))
            status = str(s.get("status", ""))
            mastery = float(s.get("mastery")) if s.get("mastery") is not None else None
            evidence = str(s.get("evidence", ""))
            recently_same = False
            for p in existing_progress:
                if p.get("topic") == topic and (course_id is None or p.get("course_id") == course_id):
                    t = parse_time(p.get("last_review_at") or p.get("next_review_at"))
                    if t and (now - t) <= throttle_window:
                        recently_same = True
                        break
            if recently_same:
                prog_skipped += 1
                continue

            next_review_at = s.get("next_review_at")
            ok = upsert_learning_progress(
                user_id=user_id,
                course_id=course_id,
                topic=topic,
                status=status,
                mastery=mastery,
                evidence=evidence,
                next_review_at=next_review_at,
            )
            if ok:
                prog_written += 1
            else:
                prog_failed += 1
        except Exception as exc:
            prog_failed += 1
            logging.warning(f"persist learning progress failed: {exc}")

    logging.info(
        {
            "user_id": user_id,
            "pref_rule_hits": pref_hit,
            "pref_written": pref_written,
            "pref_skipped": pref_skipped,
            "pref_failed": pref_failed,
            "progress_rule_hits": prog_hit,
            "progress_written": prog_written,
            "progress_skipped": prog_skipped,
            "progress_failed": prog_failed,
        }
    )


def select_relevant_memory(memory_text: str, query: str | None, top_k: int = 6) -> str:
    if not memory_text:
        return ""
    lines = [ln.strip() for ln in memory_text.splitlines() if ln.strip()]
    if not lines:
        return ""
    if not query:
        return "\n".join(lines[:top_k])

    try:
        q_vec = embed_text(str(query))
        scored = []
        for ln in lines:
            try:
                ln_vec = embed_text(ln)
                score = cosine_similarity(q_vec, ln_vec)
            except Exception:
                score = -1.0
            scored.append((score, ln))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [ln for sc, ln in scored[:top_k] if sc is not None]
        if all((sc <= 0 for sc, _ in scored)):
            raise RuntimeError("embedding scores non-positive, fallback")
        return "\n".join(selected)
    except Exception:
        q_low = str(query).lower()
        q_words = set(re.findall(r"[\w\u4e00-\u9fff]+", q_low))
        scored = []
        for ln in lines:
            ln_low = ln.lower()
            ln_words = set(re.findall(r"[\w\u4e00-\u9fff]+", ln_low))
            overlap = len(q_words & ln_words)
            scored.append((overlap, ln))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [ln for sc, ln in scored if sc > 0][:top_k]
        if not selected:
            return "\n".join(lines[:top_k])
        return "\n".join(selected)


def inject_memory_as_system(
    messages: List[Dict[str, str]],
    memory_text: str,
    query: str | None = None,
    top_k: int | None = None,
) -> List[Dict[str, str]]:
    text = (memory_text or "").strip()
    if not text:
        return messages
    if top_k is None:
        top_k = getattr(settings, "long_memory_top_k", 5)

    selected = select_relevant_memory(text, query=query, top_k=top_k)
    if not selected:
        return messages

    memory_msg = {
        "role": "system",
        "content": (
            "【用户记忆（仅作个性化参考）】\n"
            "以下为与当前问题最相关的记忆片段；请仅在直接相关的问题中使用，"
            "并勿将其作为新知识去扩展或推断。\n\n"
            f"{selected}\n\n"
            "若信息不足，请写“资料中未找到”或明确告知不确定性。"
        ),
    }
    marker = "【用户记忆（仅作个性化参考）】"
    if any(m.get("role") == "system" and marker in m.get("content", "") for m in messages):
        return messages
    first_system_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
    if first_system_idx >= 0:
        return messages[: first_system_idx + 1] + [memory_msg] + messages[first_system_idx + 1 :]
    return [memory_msg] + messages


def get_latest_user_query(messages: List[Dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", "")).strip()
    return ""


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
    candidates = list_chunks_with_embedding(document_id=document_id, limit=candidate_limit)
    if not candidates:
        return []
    ranked = rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)
    return ranked


def _brief_text(text: str, max_len: int = 80) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[:max_len] + "..."


def build_reference_items(chunks: List[Dict[str, object]], max_items: int = 8) -> List[Dict[str, object]]:
    refs: List[Dict[str, object]] = []
    for i, c in enumerate(chunks[:max_items], start=1):
        score_val = c.get("score")
        refs.append(
            {
                "ref_id": f"参考{i}",
                "page_no": c.get("page_no"),
                "summary": _brief_text(c.get("content", ""), max_len=100),
                "doucument_title": c.get("document_title", "未知文档"),
                "score": float(score_val) if isinstance(score_val, (int, float)) else None,
            }
        )
    return refs


def build_retrieval_context(chunks: List[Dict[str, object]]) -> str:
    if not chunks:
        return ""
    lines = [
        "以下是可参考的资料片段，请优先依据这些内容回答；",
        "如果资料不足，请明确说“资料中未找到”。",
        "",
    ]
    for i, c in enumerate(chunks, start=1):
        title = str(c.get("document_title", "未知文档"))
        page_no = c.get("page_no")
        page_text = f"第{page_no}页" if page_no is not None else "未知页码"
        content = str(c.get("content", "")).strip()
        score = c.get("score")
        score_text = f"{float(score):.4f}" if isinstance(score, (int, float)) else "N/A"

        lines.append(f"[参考{i}] 来源：{title} | {page_text} | 相似度：{score_text}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def inject_retrieval_as_system(messages: List[Dict[str, str]], context_text: str) -> List[Dict[str, str]]:
    text = context_text.strip()
    if not text:
        return messages
    retrieval_msg = {
        "role": "system",
        "content": (
            "以下是检索到的学习资料片段，供你参考：\n\n"
            f"{text}\n\n"
            "使用说明：\n"
            "1. 如果用户的问题与资料相关，请优先基于资料内容回答，可注明出处。\n"
            "2. 如果用户的问题与资料无关（例如闲聊、讲笑话、通用知识等），请直接用你自己的知识正常回答，不要拒绝。\n"
            "3. 如果资料里没有某个知识点，可以说资料中未提到，然后用自己的知识回答。\n"
            "4. 不要因为资料里没有提到而拒绝回答用户的任何问题。"
        ),
    }
    first_system_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
    if first_system_idx >= 0:
        return messages[: first_system_idx + 1] + [retrieval_msg] + messages[first_system_idx + 1 :]
    return [retrieval_msg] + messages


def retrieve_chunks_multi(
    query: str,
    document_ids: List[int],
    top_k: int = 5,
    candidate_limit: int = 1000,
) -> List[Dict[str, object]]:
    if not document_ids or not query.strip():
        return []
    query_vec = embed_text(query.strip())
    candidates = list_chunks_with_embedding_multi(document_ids=document_ids, limit=candidate_limit)
    if not candidates:
        return []
    return rank_chunks(query_vec=query_vec, chunks=candidates, top_k=top_k)


def build_web_context(results: List[Dict[str, object]]) -> str:
    if not results:
        return ""
    lines = ["【联网搜索结果】以下为实时搜索到的参考信息：", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"[网络{i}] {r.get('title', '')}")
        lines.append(f"来源：{r.get('url', '')}")
        lines.append(r.get("snippet", "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def inject_web_context_as_system(messages: List[Dict[str, str]], web_context: str) -> List[Dict[str, str]]:
    if not web_context.strip():
        return messages
    web_msg = {
        "role": "system",
        "content": (
            "以下是联网搜索到的最新信息，供你参考。"
            "请结合资料和搜索结果回答，并在必要时注明信息来源。\n\n"
            f"{web_context}"
        ),
    }
    marker = "【联网搜索结果】"
    if any(marker in m.get("content", "") for m in messages if m.get("role") == "system"):
        return messages
    first_sys = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
    if first_sys >= 0:
        return messages[: first_sys + 1] + [web_msg] + messages[first_sys + 1 :]
    return [web_msg] + messages


def _build_input_data(payload: Any, final_messages: List[Dict[str, str]]) -> Dict[str, Any]:
    input_data: Dict[str, Any] = {"messages": final_messages}
    if payload.image_url:
        input_data["image_url"] = payload.image_url
    if payload.audio_url:
        input_data["audio_url"] = payload.audio_url
    if payload.files:
        input_data["files"] = payload.files
    return input_data


def _build_user_error_message(msg: str) -> tuple[str, str]:
    if "http 429" in msg or "rate-limited" in msg:
        return "当前请求较多，我这边有点忙，稍后再试一下。", "RATE_LIMIT"
    if "timeout" in msg.lower() or "timed out" in msg:
        return "这次请求超时了，请简化问题后再试。", "TIMEOUT"
    if "WinError 10054" in msg or "Remote end closed connection" in msg:
        return "网络连接不太稳定，请稍后重试。", "CONNECTION_ERROR"
    return "服务暂时不可用，请稍后再试。", "UNKNOWN"


async def handle_chat(payload: Any) -> Dict[str, Any]:
    start = time.time()
    session_id = payload.session_id.strip() if payload.session_id else "default"
    retrieved_chunks: List[Dict[str, object]] = []
    retrieval_context = ""
    try:
        if not session_id:
            session_id = "default"
        history = SESSION_STORE.get(session_id, [])
        raw_messages = [m.model_dump() for m in payload.messages]
        raw_messages = [m for m in raw_messages if m.get("content")]
        merged_messages = history + raw_messages
        merged_messages = [m for m in merged_messages if m.get("content")]

        short_mem = get_short_term_memory(
            session_id=session_id,
            merged_messages=merged_messages,
            rounds=settings.short_memory_rounds,
        )
        user_id = payload.user_id.strip() if payload.user_id else "default_user"
        if not user_id:
            user_id = "default_user"

        try:
            pref_items, progress_items = await asyncio.gather(
                run_in_threadpool(
                    list_user_preferences,
                    user_id=user_id,
                    limit=settings.long_memory_top_k,
                ),
                run_in_threadpool(
                    list_learning_progress,
                    user_id=user_id,
                    course_id=payload.document_id,
                    limit=settings.progress_top_k,
                ),
            )
        except Exception as exc:
            logging.warning(f"获取用户偏好失败: {exc}")
            pref_items = []
            progress_items = []

        try:
            reminders = await run_in_threadpool(
                list_user_reminders,
                user_id=user_id,
                lookahead_hours=48,
            )
            if reminders:
                progress_items = (progress_items or []) + reminders
        except Exception as exc:
            logging.warning(f"获取用户提醒失败: {exc}")

        memory_text = build_memory_context_text(
            short_mem=short_mem,
            pref_items=pref_items,
            progress_items=progress_items,
            pref_top_k=settings.long_memory_top_k,
            progress_top_k=settings.progress_top_k,
        )
        query = get_latest_user_query(merged_messages)
        resolved_coursed_id: Optional[int] = None
        if payload.document_id:
            try:
                doc_detail = await run_in_threadpool(get_document_detail, payload.document_id)
                if doc_detail:
                    resolved_coursed_id = int(doc_detail.get("course_id") or 0)
            except Exception as exc:
                logging.warning(f"获取文档{payload.document_id}详情失败: {exc}")
        pref_signals, progress_signals = extract_memory_signals(
            user_text=query,
            document_id=resolved_coursed_id,
        )
        await run_in_threadpool(
            persist_memory_signals,
            user_id=user_id,
            pref_signals=pref_signals,
            progress_signals=progress_signals,
        )

        if payload.use_retrieval:
            eff_doc_ids = (
                list(payload.document_ids)
                if payload.document_ids
                else ([payload.document_id] if payload.document_id else [])
            )
            if eff_doc_ids:
                retrieved_chunks = await run_in_threadpool(
                    retrieve_chunks_multi,
                    query=query,
                    document_ids=eff_doc_ids,
                    top_k=20,
                    candidate_limit=2000,
                )
            else:
                retrieved_chunks = await run_in_threadpool(
                    retrieve_chunks_for_chat,
                    query=query,
                    document_id=payload.document_id,
                    top_k=20,
                    candidate_limit=2000,
                )
            retrieval_context = build_retrieval_context(retrieved_chunks)

        web_context = ""
        if payload.use_web_search:
            try:
                web_results = web_search(query, top_k=5)
                web_context = build_web_context(web_results)
            except Exception as web_exc:
                logging.warning(f"web search failed: {web_exc}")

        final_messages = inject_system_prompt(merged_messages)
        if settings.memory_enabled:
            final_messages = inject_memory_as_system(final_messages, memory_text)
        if retrieval_context:
            final_messages = inject_retrieval_as_system(final_messages, retrieval_context)
        if web_context:
            final_messages = inject_web_context_as_system(final_messages, web_context)

        input_data = _build_input_data(payload, final_messages)
        result = await run_in_threadpool(smart_model_dispatch, input_data)

        latency_ms = int((time.time() - start) * 1000)
        logging.info(
            f"chat of session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms"
        )
        merged_messages.append({"role": "assistant", "content": result["reply"]})
        SESSION_STORE[session_id] = merged_messages[-settings.history_max_rounds * 2 :]
        references = build_reference_items(retrieved_chunks) if payload.use_retrieval else []
        return {
            "reply": str(result.get("reply", "")),
            "latency_ms": int(result.get("latency_ms", 0)),
            "reference": references,
        }
    except Exception as exc:
        msg = str(exc)
        latency_ms = int((time.time() - start) * 1000)
        logging.error(
            f"chat fail session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms err={msg}"
        )
        user_msg, error_type = _build_user_error_message(msg)
        try:
            append_error_row(session_id, latency_ms, error_type, msg)
        except Exception as log_exc:
            logging.error(f"append_error_row failed: {log_exc}")
        raise HTTPException(status_code=500, detail=user_msg)


def create_chat_stream_response(payload: Any) -> StreamingResponse:
    start = time.time()
    session_id = payload.session_id.strip() if payload.session_id else "default"
    if not session_id:
        session_id = "default"

    history = SESSION_STORE.get(session_id, [])
    raw_messages = [m.model_dump() for m in payload.messages]
    raw_messages = [m for m in raw_messages if m.get("content")]
    merged_messages = [m for m in (history + raw_messages) if m.get("content")]
    final_messages = inject_system_prompt(merged_messages)

    if settings.memory_enabled:
        try:
            short_mem = get_short_term_memory(
                session_id=session_id,
                merged_messages=merged_messages,
                rounds=settings.short_memory_rounds,
            )
            memory_text = build_memory_context_text(
                short_mem=short_mem,
                pref_items=[],
                progress_items=[],
                pref_top_k=0,
                progress_top_k=0,
            )
            query = get_latest_user_query(merged_messages)
            final_messages = inject_memory_as_system(final_messages, memory_text, query=query)
        except Exception as exc:
            logging.warning(f"chat_stream memory inject failed: {exc}")

    def event_gen():
        try:
            if payload.image_url or payload.audio_url or payload.files:
                input_data = _build_input_data(payload, final_messages)
                result = smart_model_dispatch(input_data)
                reply = str(result.get("reply", "")).strip()
                if reply:
                    yield f"data: {json.dumps({'delta': reply}, ensure_ascii=False)}\n\n"
                latency_ms = int((time.time() - start) * 1000)
                yield f"data: {json.dumps({'done': True, 'reply': reply, 'latency_ms': latency_ms}, ensure_ascii=False)}\n\n"
                merged_messages.append({"role": "assistant", "content": reply})
                SESSION_STORE[session_id] = merged_messages[-settings.history_max_rounds * 2 :]
                return

            reply_chunks: List[str] = []
            try:
                for delta in remote_stream_reply(final_messages):
                    reply_chunks.append(delta)
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            except Exception as stream_exc:
                logging.warning(f"chat stream upstream failed, fallback to non-stream: {stream_exc}")
                fallback_result = smart_model_dispatch({"messages": final_messages})
                fallback_reply = str(fallback_result.get("reply", "")).strip()
                if not fallback_reply:
                    raise stream_exc
                reply_chunks = [fallback_reply]
                yield f"data: {json.dumps({'delta': fallback_reply}, ensure_ascii=False)}\n\n"

            reply = "".join(reply_chunks).strip()
            latency_ms = int((time.time() - start) * 1000)
            merged_messages.append({"role": "assistant", "content": reply})
            SESSION_STORE[session_id] = merged_messages[-settings.history_max_rounds * 2 :]
            yield f"data: {json.dumps({'done': True, 'reply': reply, 'latency_ms': latency_ms}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            msg = str(exc)
            latency_ms = int((time.time() - start) * 1000)
            logging.error(
                f"chat stream fail session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms err={msg}"
            )
            yield f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
