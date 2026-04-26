import os
from dataclasses import dataclass

from server.dialogue.personas import PERSONAS


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
    remote_primary_api_base_url: str = os.getenv("REMOTE_PRIMARY_API_BASE_URL", "https://api.siliconflow.cn/v1")
    remote_primary_api_key: str = os.getenv("REMOTE_PRIMARY_API_KEY", "")
    remote_primary_model: str = os.getenv("REMOTE_PRIMARY_MODEL", "Pro/deepseek-ai/DeepSeek-V3.2")

    # Embedding
    embedding_api_base_url: str = os.getenv("EMBEDDING_API_BASE_URL", "https://api.siliconflow.cn/v1")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    embedding_timeout_sec: int = int(os.getenv("EMBEDDING_TIMEOUT_SEC", "60"))

    # Vision fallback model
    remote_vision_model: str = os.getenv("REMOTE_VISION_MODEL", "Pro/moonshotai/Kimi-K2.5")

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
    persona_id: str = os.getenv("PERSONA_ID", "student_friend")
    _default_persona_prompt: str = (
        "你是校园学习伙伴。语气友好、鼓励、简洁。"
        "回答控制在 3 到 6 句，先结论后行动建议。"
        "不说教，不阴阳怪气，不输出空泛鸡汤。"
    )

    # Companion prompt template
    companion_system_prompt_template: str = os.getenv(
        "COMPANION_SYSTEM_PROMPT_TEMPLATE",
        (
            "你是一个实时桌面陪伴助手（persona_id={persona_id}, scene={scene}）。"
            "请只输出 JSON，不要输出额外解释，格式必须是："
            "{\"reply\":\"...\",\"tts_text\":\"...\",\"emotion\":\"neutral|smile|sad|angry|surprised\",\"action_intents\":[{\"type\":\"live2d_expression|live2d_motion|live2d_look_at|game_control\",\"payload\":{}}]}。"
            "reply 给 UI 展示；tts_text 给语音播报（可比 reply 更短）。"
            "action_intents 可以为空数组。"
        ),
    )
    companion_tts_max_chars: int = int(os.getenv("COMPANION_TTS_MAX_CHARS", "120"))

    @property
    def persona_system_prompt(self) -> str:
        try:
            persona = PERSONAS.get(self.persona_id)
            if persona and isinstance(persona, dict) and persona.get("system_prompt"):
                return persona.get("system_prompt")
        except Exception:
            pass
        return self._default_persona_prompt

    def build_companion_prompt(self, persona_id: str, scene: str) -> str:
        text = str(self.companion_system_prompt_template or "")
        return (
            text.replace("{persona_id}", persona_id or "default_companion")
            .replace("{scene}", scene or "desktop")
        )

    # History and memory
    history_max_rounds: int = int(os.getenv("HISTORY_MAX_ROUNDS", "6"))
    memory_enabled: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
    short_memory_rounds: int = int(os.getenv("SHORT_MEMORY_ROUNDS", "6"))
    long_memory_top_k: int = int(os.getenv("LONG_MEMORY_TOP_K", "5"))
    progress_top_k: int = int(os.getenv("PROGRESS_TOP_K", "5"))
    throttle_window_minutes: int = int(os.getenv("THROTTLE_WINDOW_MINUTES", "60"))


settings = Settings()
