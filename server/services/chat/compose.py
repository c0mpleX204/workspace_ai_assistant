from __future__ import annotations

from typing import Dict, List

from server.config.config import settings
from server.services.chat.memory import inject_memory_as_system, inject_summary_as_system
from server.services.chat.messages import _insert_system_after_primary, inject_system_prompt

def add_recall_ctx(messages: List[Dict[str, str]], context_text: str) -> List[Dict[str, str]]:
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
    return _insert_system_after_primary(messages, retrieval_msg, marker="以下是检索到的学习资料片段")


def add_web_ctx(messages: List[Dict[str, str]], web_context: str) -> List[Dict[str, str]]:
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
    return _insert_system_after_primary(messages, web_msg, marker=marker)


def add_command_ctx(messages: List[Dict[str, str]], command_context: str) -> List[Dict[str, str]]:
    if not command_context.strip():
        return messages
    command_msg = {
        "role": "system",
        "content": (
            "以下是平台刚刚在项目终端中执行命令得到的结果。"
            "请基于 stdout/stderr/exit_code 解释结果，并在需要时给出下一步建议。\n\n"
            f"{command_context}"
        ),
    }
    return _insert_system_after_primary(messages, command_msg, marker="【命令行执行结果】")


def add_project_memory_ctx(messages: List[Dict[str, str]], project_memory_text: str) -> List[Dict[str, str]]:
    text = str(project_memory_text or "").strip()
    if not text:
        return messages
    project_memory_msg = {
        "role": "system",
        "content": (
            "Project memory for this workspace. It may include durable background, progress, "
            "user-emphasized constraints, and open questions from earlier project chats. "
            "Use it only as project context; the latest user message overrides it on conflict.\n\n"
            f"{text}"
        ),
    }
    return _insert_system_after_primary(messages, project_memory_msg, marker="Project memory for this workspace")


def build_final_messages(
    merged_messages: List[Dict[str, str]],
    *,
    persona_prompt: str = "",
    conversation_summary: str = "",
    memory_text: str = "",
    query: str | None = None,
    recall_ctx: str = "",
    web_context: str = "",
    command_context: str = "",
    project_memory_text: str = "",
) -> List[Dict[str, str]]:
    final_messages = inject_system_prompt(merged_messages, persona_prompt=persona_prompt)
    final_messages = inject_summary_as_system(final_messages, conversation_summary)
    if project_memory_text:
        final_messages = add_project_memory_ctx(final_messages, project_memory_text)
    if settings.memory_enabled:
        final_messages = inject_memory_as_system(final_messages, memory_text, query=query)
    if recall_ctx:
        final_messages = add_recall_ctx(final_messages, recall_ctx)
    if web_context:
        final_messages = add_web_ctx(final_messages, web_context)
    if command_context:
        final_messages = add_command_ctx(final_messages, command_context)
    return final_messages
