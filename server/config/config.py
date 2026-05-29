import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.dialogue.personas import PERSONAS
from server.dialogue.prompts import (
    DEFAULT_PERSONA_ID,
    DEFAULT_PERSONA_PROMPT,
)


DEFAULT_DEEPSEEK_API_BASE_URL = "https://api.deepseek.com"
DEFAULT_FAST_MODEL = "deepseek-v4-flash"
DEFAULT_HEAVY_MODEL = "deepseek-v4-pro"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROVIDER_CONFIG_PATH = Path(
    os.getenv("PROVIDER_CONFIG_PATH", str(PROJECT_ROOT / "data" / "runtime" / "provider_config.json"))
)


def _load_runtime_provider_config() -> dict[str, Any]:
    try:
        if not RUNTIME_PROVIDER_CONFIG_PATH.is_file():
            return {}
        data = json.loads(RUNTIME_PROVIDER_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_RUNTIME_PROVIDER_CONFIG = _load_runtime_provider_config()


def _provider_value(key: str, env_name: str, default: str) -> str:
    env_value = os.getenv(env_name)
    if env_value is not None:
        return env_value
    value = _RUNTIME_PROVIDER_CONFIG.get(key, default)
    return str(value or "")


@dataclass
class Settings:
    # Generation
    max_new_tokens: int = int(os.getenv("MAX_NEW_TOKENS", "256"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    top_p: float = float(os.getenv("TOP_P", "0.9"))

    # Service
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "info")

    # Primary chat model (OpenAI-compatible)
    remote_primary_api_base_url: str = _provider_value(
        "api_base_url",
        "REMOTE_PRIMARY_API_BASE_URL",
        DEFAULT_DEEPSEEK_API_BASE_URL,
    )
    remote_primary_api_key: str = _provider_value("api_key", "REMOTE_PRIMARY_API_KEY", "")
    remote_fast_model: str = _provider_value("fast_model", "REMOTE_FAST_MODEL", DEFAULT_FAST_MODEL)
    remote_heavy_model: str = _provider_value("heavy_model", "REMOTE_HEAVY_MODEL", DEFAULT_HEAVY_MODEL)
    remote_primary_model: str = _provider_value("primary_model", "REMOTE_PRIMARY_MODEL", remote_fast_model)

    # Embedding
    embedding_api_base_url: str = os.getenv("EMBEDDING_API_BASE_URL", "https://api.siliconflow.cn/v1")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    embedding_timeout_sec: int = int(os.getenv("EMBEDDING_TIMEOUT_SEC", "60"))

    # Vision fallback model
    remote_vision_model: str = os.getenv("REMOTE_VISION_MODEL", remote_heavy_model)

    # STT
    stt_provider: str = os.getenv("STT_PROVIDER", "sherpa_sense_voice")
    stt_model: str = os.getenv("STT_MODEL", "FunAudioLLM/SenseVoiceSmall")
    stt_fallback_model: str = os.getenv("STT_FALLBACK_MODEL", "")
    local_stt_sherpa_model_dir: str = os.getenv("LOCAL_STT_SHERPA_MODEL_DIR", "D:\\models\\sherpa-sense-voice")
    local_stt_sherpa_model_file: str = os.getenv("LOCAL_STT_SHERPA_MODEL_FILE", "model.int8.onnx")
    local_stt_sherpa_tokens_file: str = os.getenv("LOCAL_STT_SHERPA_TOKENS_FILE", "tokens.txt")
    local_stt_sherpa_provider: str = os.getenv("LOCAL_STT_SHERPA_PROVIDER", "cpu")
    local_stt_sherpa_num_threads: int = int(os.getenv("LOCAL_STT_SHERPA_NUM_THREADS", "2"))
    local_stt_sherpa_sample_rate: int = int(os.getenv("LOCAL_STT_SHERPA_SAMPLE_RATE", "16000"))
    local_stt_sherpa_language: str = os.getenv("LOCAL_STT_SHERPA_LANGUAGE", "auto")
    local_stt_sherpa_use_itn: bool = os.getenv("LOCAL_STT_SHERPA_USE_ITN", "false").lower() == "true"
    stt_noise_blocklist: str = os.getenv(
        "STT_NOISE_BLOCKLIST",
        "字幕制作人,字幕製作人,字幕by,Zither Harp,索兰娅",
    )

    # TTS
    tts_provider: str = os.getenv("TTS_PROVIDER", "auto_local_first")
    tts_model: str = os.getenv("TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
    tts_voice: str = os.getenv("TTS_VOICE", "FunAudioLLM/CosyVoice2-0.5B:anna")
    local_gpt_sovits_base_url: str = os.getenv("LOCAL_GPT_SOVITS_BASE_URL", "http://127.0.0.1:9880")
    local_gpt_sovits_tts_path: str = os.getenv("LOCAL_GPT_SOVITS_TTS_PATH", "/tts")
    local_gpt_sovits_ref_audio_path: str = os.getenv("LOCAL_GPT_SOVITS_REF_AUDIO_PATH", "")
    local_gpt_sovits_prompt_text: str = os.getenv("LOCAL_GPT_SOVITS_PROMPT_TEXT", "")
    local_gpt_sovits_prompt_lang: str = os.getenv("LOCAL_GPT_SOVITS_PROMPT_LANG", "zh")
    local_gpt_sovits_text_lang: str = os.getenv("LOCAL_GPT_SOVITS_TEXT_LANG", "zh")
    local_gpt_sovits_media_type: str = os.getenv("LOCAL_GPT_SOVITS_MEDIA_TYPE", "wav")
    local_gpt_sovits_timeout_sec: int = int(os.getenv("LOCAL_GPT_SOVITS_TIMEOUT_SEC", "45"))

    # Backup channel
    remote_backup_api_base_url: str = os.getenv("REMOTE_BACKUP_API_BASE_URL", "")
    remote_backup_api_key: str = os.getenv("REMOTE_BACKUP_API_KEY", "")
    remote_backup_model: str = os.getenv("REMOTE_BACKUP_MODEL", "")

    # Routing strategy
    remote_strategy: str = os.getenv("REMOTE_STRATEGY", "primary_only")
    remote_connect_timeout_sec: int = int(os.getenv("REMOTE_CONNECT_TIMEOUT_SEC", "8"))
    remote_request_retries: int = int(os.getenv("REMOTE_REQUEST_RETRIES", "1"))
    remote_timeout_sec: int = int(os.getenv("REMOTE_TIMEOUT_SEC", "28"))
    remote_stream_timeout_sec: int = int(os.getenv("REMOTE_STREAM_TIMEOUT_SEC", "20"))
    stt_timeout_sec: int = int(os.getenv("STT_TIMEOUT_SEC", "20"))
    stt_max_retries: int = int(os.getenv("STT_MAX_RETRIES", "1"))
    tts_timeout_sec: int = int(os.getenv("TTS_TIMEOUT_SEC", "30"))

    # Persona
    persona_id: str = os.getenv("PERSONA_ID", DEFAULT_PERSONA_ID)
    _default_persona_prompt: str = DEFAULT_PERSONA_PROMPT

    @property
    def persona_system_prompt(self) -> str:
        try:
            persona = PERSONAS.get(self.persona_id)
            if persona and isinstance(persona, dict) and persona.get("system_prompt"):
                return persona.get("system_prompt")
        except Exception:
            pass
        return self._default_persona_prompt

    # History and memory
    history_max_rounds: int = int(os.getenv("HISTORY_MAX_ROUNDS", "6"))
    memory_enabled: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
    short_memory_rounds: int = int(os.getenv("SHORT_MEMORY_ROUNDS", "6"))
    long_memory_top_k: int = int(os.getenv("LONG_MEMORY_TOP_K", "5"))
    progress_top_k: int = int(os.getenv("PROGRESS_TOP_K", "5"))
    throttle_window_minutes: int = int(os.getenv("THROTTLE_WINDOW_MINUTES", "60"))

    # Extended thinking (reasoning / chain-of-thought)
    thinking_enabled: bool = os.getenv("THINKING_ENABLED", "true").lower() == "true"
    thinking_model: str = os.getenv("THINKING_MODEL", remote_heavy_model)

    # Function calling
    function_calling_enabled: bool = os.getenv("FUNCTION_CALLING_ENABLED", "true").lower() == "true"

    # Sub-agent orchestration
    subagent_enabled: bool = os.getenv("SUBAGENT_ENABLED", "true").lower() == "true"
    subagent_max_workers: int = int(os.getenv("SUBAGENT_MAX_WORKERS", "4"))


settings = Settings()


def mask_secret(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "••••"
    return f"{text[:3]}••••{text[-4:]}"


def get_provider_config_public() -> dict[str, Any]:
    return {
        "api_base_url": settings.remote_primary_api_base_url,
        "api_key_masked": mask_secret(settings.remote_primary_api_key),
        "has_api_key": bool(settings.remote_primary_api_key),
        "fast_model": settings.remote_fast_model,
        "heavy_model": settings.remote_heavy_model,
        "primary_model": settings.remote_primary_model,
        "config_path": str(RUNTIME_PROVIDER_CONFIG_PATH),
    }


def save_provider_config(
    *,
    api_base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    current = _load_runtime_provider_config()
    incoming_key = None if api_key is None else str(api_key).strip()
    if incoming_key and set(incoming_key) <= {"•", "*", "."}:
        incoming_key = None
    next_config = {
        "api_base_url": str(
            api_base_url
            if api_base_url is not None
            else current.get("api_base_url", settings.remote_primary_api_base_url)
        ).strip().rstrip("/"),
        "api_key": (
            incoming_key
            if incoming_key is not None
            else str(current.get("api_key", settings.remote_primary_api_key) or "")
        ),
        "fast_model": DEFAULT_FAST_MODEL,
        "heavy_model": DEFAULT_HEAVY_MODEL,
        "primary_model": DEFAULT_FAST_MODEL,
    }
    if not next_config["api_base_url"]:
        next_config["api_base_url"] = DEFAULT_DEEPSEEK_API_BASE_URL

    RUNTIME_PROVIDER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PROVIDER_CONFIG_PATH.write_text(
        json.dumps(next_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    settings.remote_primary_api_base_url = next_config["api_base_url"]
    settings.remote_primary_api_key = next_config["api_key"]
    settings.remote_fast_model = next_config["fast_model"]
    settings.remote_heavy_model = next_config["heavy_model"]
    settings.remote_primary_model = next_config["primary_model"]
    return get_provider_config_public()
