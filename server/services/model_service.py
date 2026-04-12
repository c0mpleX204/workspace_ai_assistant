import json
import time
from typing import Dict, Iterator, List

import requests

from server.config.config import settings
from .text_utils import repair_mojibake_text


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


def _remote_generate_reply_by_provider(
    messages: List[Dict[str, str]],
    provider: Dict[str, str],
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
) -> Dict[str, object]:
    generation = generation or {}
    req_model = str(model_override or provider["model"])
    req_temperature = float(generation.get("temperature", settings.temperature))
    req_top_p = float(generation.get("top_p", settings.top_p))
    req_max_tokens = int(generation.get("max_tokens", settings.max_new_tokens))

    base_url = provider["api_base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": req_model,
        "messages": messages,
        "temperature": req_temperature,
        "top_p": req_top_p,
        "max_tokens": req_max_tokens,
    }
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
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    content = repair_mojibake_text(str(content))
    latency_ms = int((time.time() - start) * 1000)
    return {
        "reply": str(content).strip(),
        "latency_ms": latency_ms,
    }


def _remote_generate_reply(
    messages: List[Dict[str, str]],
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
) -> Dict[str, object]:
    providers = _build_remote_providers()
    errors: List[str] = []
    for provider in providers:
        try:
            return _remote_generate_reply_by_provider(
                messages,
                provider,
                model_override=model_override,
                generation=generation,
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


def generate_reply(messages: List[Dict[str, str]]) -> Dict[str, object]:
    if not messages:
        raise ValueError("messages cannot be empty")
    return _remote_generate_reply(messages)


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


def _inject_image_into_messages(messages: List[Dict[str, str]], image_url: str) -> List[Dict]:
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


def _remote_generate_reply_vision(
    messages: List[Dict],
    image_url: str,
    model_override: str | None = None,
    generation: Dict[str, object] | None = None,
) -> Dict[str, object]:
    msgs_with_image = _inject_image_into_messages(messages, image_url)
    vision_provider = {
        "name": "vision",
        "api_base_url": settings.remote_primary_api_base_url,
        "api_key": settings.remote_primary_api_key,
        "model": settings.remote_vision_model,
    }
    return _remote_generate_reply_by_provider(
        msgs_with_image,
        vision_provider,
        model_override=model_override,
        generation=generation,
    )


def remote_stream_reply(messages: List[Dict[str, str]]) -> Iterator[str]:
    providers = _build_remote_providers()
    provider = providers[0]
    base_url = provider["api_base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": provider["model"],
        "messages": messages,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_tokens": settings.max_new_tokens,
        "stream": True,
    }

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
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = "".join(
                            part.get("text", "") for part in content if isinstance(part, dict)
                        )
                    content = repair_mojibake_text(str(content))
                    if content:
                        yield content
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

                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content", "")
                if isinstance(delta, list):
                    delta = "".join(
                        part.get("text", "") for part in delta if isinstance(part, dict)
                    )
                delta = repair_mojibake_text(str(delta))
                if delta:
                    yield delta
    except Exception as exc:
        raise RuntimeError(f"remote stream request failed: {exc}") from exc


def smart_model_dispatch(input_data: dict) -> dict:
    messages = input_data.get("messages", [])
    image_url = input_data.get("image_url", "")
    model_override = input_data.get("model")
    generation = input_data.get("generation")

    if image_url or _has_image(input_data):
        return _remote_generate_reply_vision(
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
    )

