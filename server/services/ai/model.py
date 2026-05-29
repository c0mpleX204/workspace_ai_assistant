import json
import time
from typing import Dict, Iterator, List

import requests

from server.config.config import settings
from server.utils.text_utils import repair_mojibake_text


def normalize_token_usage(raw_usage: object) -> Dict[str, int | None]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    completion_details = (
        usage.get("completion_tokens_details")
        if isinstance(usage.get("completion_tokens_details"), dict)
        else {}
    )

    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    cache_hit_tokens = (
        usage.get("prompt_cache_hit_tokens")
        if usage.get("prompt_cache_hit_tokens") is not None
        else prompt_details.get("cached_tokens")
    )
    cache_miss_tokens = usage.get("prompt_cache_miss_tokens")
    reasoning_tokens = completion_details.get("reasoning_tokens")

    def as_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "input_tokens": as_int(input_tokens),
        "output_tokens": as_int(output_tokens),
        "total_tokens": as_int(total_tokens),
        "cache_hit_tokens": as_int(cache_hit_tokens),
        "cache_miss_tokens": as_int(cache_miss_tokens),
        "reasoning_tokens": as_int(reasoning_tokens),
    }


def _response_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts: List[str] = []
        for part in value:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if text is None:
                text = part.get("content")
            if text is not None:
                parts.append(str(text))
        return repair_mojibake_text("".join(parts))
    return repair_mojibake_text(str(value))


def _build_remote_providers() -> List[Dict[str, str]]:
    providers: List[Dict[str, str]] = []
    if settings.remote_primary_api_key:
        providers.append(
            {
                "name": "primary",
                "api_base_url": settings.remote_primary_api_base_url,
                "api_key": settings.remote_primary_api_key,
                "model": settings.remote_primary_model,
            }
        )
    if settings.remote_strategy == "primary_then_backup" and settings.remote_backup_api_key:
        if not settings.remote_backup_api_base_url or not settings.remote_backup_model:
            raise ValueError(
                "Backup provider enabled but REMOTE_BACKUP_API_BASE_URL or REMOTE_BACKUP_MODEL is empty"
            )
        providers.append(
            {
                "name": "backup",
                "api_base_url": settings.remote_backup_api_base_url,
                "api_key": settings.remote_backup_api_key,
                "model": settings.remote_backup_model,
            }
        )
    if not providers:
        raise ValueError(
            "No remote provider configured. Set REMOTE_PRIMARY_API_KEY or REMOTE_API_KEY."
        )
    return providers


def _remote_provider_reply(
    messages: List[Dict[str, str]],
    provider: Dict[str, str],
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
    thinking_enabled: bool = False,
    tools: List[Dict] | None = None,
) -> Dict[str, object]:
    generation = generation or {}
    req_model = str(model_override or provider["model"])
    req_temperature = float(generation.get("temperature", settings.temperature))
    req_top_p = float(generation.get("top_p", settings.top_p))
    req_max_tokens = int(generation.get("max_tokens", settings.max_new_tokens))

    base_url = provider["api_base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"
    payload: Dict[str, object] = {
        "model": req_model,
        "messages": messages,
        "temperature": req_temperature,
        "top_p": req_top_p,
        "max_tokens": req_max_tokens,
    }
    if thinking_enabled:
        payload["thinking"] = {"type": "enabled"}
    if tools:
        payload["tools"] = tools
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider['api_key']}",
    }
    start = time.time()
    attempts = max(1, int(getattr(settings, "remote_request_retries", 1)) + 1)
    last_err = None
    data = None

    for idx in range(attempts):
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(
                    int(getattr(settings, "remote_connect_timeout_sec", 8)),
                    int(getattr(settings, "remote_timeout_sec", 28)),
                ),
            )
            if resp.status_code >= 400:
                snippet = (resp.text or "")[:240]
                raise RuntimeError(f"remote api http {resp.status_code}: {snippet}")
            data = resp.json()
            break
        except Exception as exc:
            last_err = exc
            if idx < attempts - 1:
                time.sleep(0.45 * (idx + 1))

    if data is None:
        raise RuntimeError(f"remote api request failed: {last_err}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"remote api invalid response: {data}")
    message = choices[0].get("message") or {}
    content = _response_text(message.get("content", ""))
    reasoning_content = _response_text(message.get("reasoning_content", ""))
    tool_calls = message.get("tool_calls") or []
    latency_ms = int((time.time() - start) * 1000)
    return {
        "reply": str(content).strip(),
        "reasoning": str(reasoning_content).strip() if reasoning_content else "",
        "tool_calls": tool_calls,
        "latency_ms": latency_ms,
        "usage": normalize_token_usage(data.get("usage")),
        "model": req_model,
        "provider": provider.get("name", "primary"),
    }


def _remote_generate_reply(
    messages: List[Dict[str, str]],
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
    thinking_enabled: bool = False,
    tools: List[Dict] | None = None,
) -> Dict[str, object]:
    providers = _build_remote_providers()
    errors: List[str] = []
    for provider in providers:
        try:
            return _remote_provider_reply(
                messages,
                provider,
                model_override=model_override,
                generation=generation,
                thinking_enabled=thinking_enabled,
                tools=tools,
            )
        except Exception as exc:
            errors.append(f"{provider['name']}: {exc}")
    raise RuntimeError("All remote providers failed: " + " | ".join(errors))


def warmup_model() -> Dict[str, str]:
    providers = _build_remote_providers()
    return {
        "status": "ok",
        "backend": "remote",
        "remote_strategy": settings.remote_strategy,
        "remote_provider_count": str(len(providers)),
        "remote_model": providers[0]["model"],
        "remote_api_base_url": providers[0]["api_base_url"],
    }


def generate_reply(
    messages: List[Dict[str, str]],
    thinking_enabled: bool = False,
    tools: List[Dict] | None = None,
) -> Dict[str, object]:
    if not messages:
        raise ValueError("messages cannot be empty")
    return _remote_generate_reply(messages, thinking_enabled=thinking_enabled, tools=tools)


def remote_tool_call_loop(
    messages: List[Dict[str, str]],
    tools: List[Dict],
    tool_handler: callable,
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
    max_rounds: int = 5,
    thinking_enabled: bool = False,
) -> Dict[str, object]:
    """Multi-turn tool calling loop.

    Sends messages with tools to the model. If the model returns tool_calls,
    each is dispatched to tool_handler(name, arguments) and the result is
    appended as a tool message.  Loops until the model returns a text reply
    or max_rounds is reached.
    """
    msgs = [dict(m) for m in messages]
    generation = generation or {}
    last_usage = None
    reasoning = ""
    all_reply = ""

    for _ in range(max_rounds):
        result = _remote_generate_reply(
            msgs,
            model_override=model_override,
            generation=generation,
            thinking_enabled=thinking_enabled,
            tools=tools,
        )
        last_usage = result.get("usage")
        if result.get("reasoning"):
            reasoning = result["reasoning"]

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            reply = str(result.get("reply") or "")
            all_reply = reply
            break

        assistant_msg: Dict[str, object] = {"role": "assistant", "content": result.get("reply") or None}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        msgs.append(assistant_msg)

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            fn_name = str(fn.get("name") or "")
            try:
                fn_args = json.loads(str(fn.get("arguments") or "{}"))
            except Exception:
                fn_args = {}
            try:
                tool_result = tool_handler(fn_name, fn_args)
                tool_result_str = str(tool_result) if not isinstance(tool_result, str) else tool_result
            except Exception as exc:
                tool_result_str = f"Error executing {fn_name}: {exc}"
            msgs.append({
                "role": "tool",
                "tool_call_id": str(tc.get("id") or ""),
                "content": tool_result_str,
            })
    else:
        all_reply = ""

    return {
        "reply": all_reply,
        "reasoning": reasoning,
        "usage": last_usage,
        "model": str(model_override or settings.remote_primary_model),
    }


def _has_image(input_data: dict) -> bool:
    image_url = input_data.get("image_url", "")
    if image_url:
        return True
    for msg in input_data.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _inject_images(messages: List[Dict[str, str]], image_url: str) -> List[Dict]:
    if not image_url:
        return messages
    msgs = [dict(m) for m in messages]
    last_user_idx = None
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        msgs.append(
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        )
        return msgs
    existing = msgs[last_user_idx]["content"]
    if isinstance(existing, list):
        existing.append({"type": "image_url", "image_url": {"url": image_url}})
    else:
        msgs[last_user_idx]["content"] = [
            {"type": "text", "text": str(existing)},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    return msgs


def _remote_vision_reply(
    messages: List[Dict],
    image_url: str,
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
) -> Dict[str, object]:
    msgs_with_image = _inject_images(messages, image_url)
    vision_provider = {
        "name": "vision",
        "api_base_url": settings.remote_primary_api_base_url,
        "api_key": settings.remote_primary_api_key,
        "model": settings.remote_vision_model,
    }
    return _remote_provider_reply(
        msgs_with_image,
        vision_provider,
        model_override=model_override,
        generation=generation,
    )


def remote_stream_events(
    messages: List[Dict[str, str]],
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
    thinking_enabled: bool = False,
    tools: List[Dict] | None = None,
) -> Iterator[Dict[str, object]]:
    generation = generation or {}
    providers = _build_remote_providers()
    provider = providers[0]
    req_model = str(model_override or provider["model"])
    req_temperature = float(generation.get("temperature", settings.temperature))
    req_top_p = float(generation.get("top_p", settings.top_p))
    req_max_tokens = int(generation.get("max_tokens", settings.max_new_tokens))
    base_url = provider["api_base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, object] = {
        "model": req_model,
        "messages": messages,
        "temperature": req_temperature,
        "top_p": req_top_p,
        "max_tokens": req_max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if thinking_enabled:
        payload["thinking"] = {"type": "enabled"}
    if tools:
        payload["tools"] = tools

    try:
        with requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(8, settings.remote_stream_timeout_sec),
        ) as resp:
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").lower()

            if "text/event-stream" not in content_type:
                obj = resp.json()
                choices = obj.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    content = _response_text(msg.get("content", ""))
                    reasoning = _response_text(msg.get("reasoning_content", ""))
                    if reasoning:
                        yield {"type": "reasoning", "delta": reasoning}
                    if content:
                        yield {"type": "delta", "delta": content}
                    tool_calls = msg.get("tool_calls") or []
                    if tool_calls:
                        yield {"type": "tool_calls", "tool_calls": tool_calls}
                if obj.get("usage"):
                    yield {"type": "usage", "usage": normalize_token_usage(obj.get("usage"))}
                return

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    break
                try:
                    obj = json.loads(data_str)
                except Exception:
                    continue

                if obj.get("usage"):
                    yield {"type": "usage", "usage": normalize_token_usage(obj.get("usage"))}

                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                reasoning_delta = _response_text(delta.get("reasoning_content", ""))
                if reasoning_delta:
                    yield {"type": "reasoning", "delta": reasoning_delta}
                content_delta = _response_text(delta.get("content", ""))
                if content_delta:
                    yield {"type": "delta", "delta": content_delta}
                tool_calls_delta = delta.get("tool_calls") or []
                if tool_calls_delta:
                    yield {"type": "tool_calls_delta", "tool_calls": tool_calls_delta}
    except Exception as exc:
        raise RuntimeError(f"remote stream request failed: {exc}") from exc


def remote_stream_reply(messages: List[Dict[str, str]]) -> Iterator[str]:
    for event in remote_stream_events(messages):
        if event.get("type") == "delta":
            yield str(event.get("delta", ""))


def smart_model_dispatch(input_data: dict) -> dict:
    messages = input_data.get("messages", [])
    image_url = input_data.get("image_url", "")
    model_override = input_data.get("model")
    generation = input_data.get("generation")
    thinking_enabled = bool(input_data.get("thinking_enabled", False))
    tools = input_data.get("tools")

    if image_url or _has_image(input_data):
        return _remote_vision_reply(
            messages,
            image_url,
            model_override=model_override,
            generation=generation,
        )

    if messages:
        return _remote_generate_reply(
            messages,
            model_override=model_override,
            generation=generation,
            thinking_enabled=thinking_enabled,
            tools=tools,
        )

    token = settings.remote_primary_api_key
    headers_form = {"Authorization": f"Bearer {token}"}

    input_type = input_data.get("type", "text")
    params = input_data.get("params", {})

    if input_type == "audio":
        if isinstance(input_data["content"], bytes):
            file_data = input_data["content"]
            file_name = params.get("file_name", "upload_audio.wav")
        else:
            file_path = input_data["content"]
            file_name = file_path.split("/")[-1]
            with open(file_path, "rb") as f:
                file_data = f.read()
        files = {"file": (file_name, file_data)}
        data = params.copy()
        url = "https://api.siliconflow.cn/v1/uploads/audio/voice"
        resp = requests.post(url, headers=headers_form, files=files, data=data, timeout=60)
        return resp.json()

    content = input_data.get("content", "")
    fallback_msgs = [{"role": "user", "content": content}]
    return _remote_generate_reply(
        fallback_msgs,
        model_override=model_override,
        generation=generation,
        thinking_enabled=thinking_enabled,
        tools=tools,
    )

