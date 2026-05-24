from __future__ import annotations

from datetime import datetime, timedelta
import logging
import re
from typing import Dict, List, Optional

import dateparser

from server.config.config import settings
from server.infra.repo import (
    list_learning_progress,
    list_user_preferences,
    upsert_learning_progress,
    upsert_user_preference,
)
from server.memory.memory_rules import RULES, normalize_pref_signal
from server.services.chat.messages import _insert_system_after_primary
from server.services.ai.embedding import cosine_similarity, embed_text

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


def build_memory_text(
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
    return _insert_system_after_primary(messages, memory_msg, marker=marker)


def inject_summary_as_system(
    messages: List[Dict[str, str]],
    summary: str,
) -> List[Dict[str, str]]:
    text = (summary or "").strip()
    if not text:
        return messages
    marker = "Conversation summary"
    if any(m.get("role") == "system" and marker in m.get("content", "") for m in messages):
        return messages
    summary_msg = {
        "role": "system",
        "content": (
            "Conversation summary (older turns only; the latest user message and "
            "recent dialogue override this if there is any conflict):\n"
            f"{text}"
        ),
    }
    return _insert_system_after_primary(messages, summary_msg, marker=marker)
