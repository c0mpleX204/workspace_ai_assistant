from typing import Dict

from fastapi import APIRouter, HTTPException

from server.agent_core.tool_registry import (
    get_tool_plugin_status,
    summarize_tool_plugin_status,
)
from server.api.schemas import ProviderConfigUpdateRequest
from server.config.config import get_provider_config_public, save_provider_config, settings
from server.services.ai.model import warmup_model

router = APIRouter(tags=["health"])


@router.get("/health")
def api_health() -> Dict[str, object]:
    try:
        warm = warmup_model()
        return {
            "ok": True,
            "chat_model": settings.remote_primary_model,
            "fast_model": settings.remote_fast_model,
            "heavy_model": settings.remote_heavy_model,
            "stt_provider": settings.stt_provider,
            "stt_model": settings.stt_model,
            "local_stt_sherpa_model_dir": settings.local_stt_sherpa_model_dir,
            "local_stt_sherpa_provider": settings.local_stt_sherpa_provider,
            "local_stt_sherpa_sample_rate": settings.local_stt_sherpa_sample_rate,
            "tts_model": settings.tts_model,
            "tts_provider": settings.tts_provider,
            "warmup": warm,
            "agent_tools": summarize_tool_plugin_status(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"health check failed: {exc}")


@router.get("/agent/tools/status")
def api_agent_tools_status() -> Dict[str, object]:
    return {
        "ok": True,
        "summary": summarize_tool_plugin_status(),
        "tools": get_tool_plugin_status(),
    }


@router.get("/settings/provider")
def api_get_provider_settings() -> Dict[str, object]:
    return {
        "ok": True,
        "provider": get_provider_config_public(),
    }


@router.put("/settings/provider")
def api_update_provider_settings(payload: ProviderConfigUpdateRequest) -> Dict[str, object]:
    provider = save_provider_config(
        api_base_url=payload.api_base_url,
        api_key=payload.api_key,
        companion_persona_prompt=payload.companion_persona_prompt,
    )
    return {
        "ok": True,
        "provider": provider,
    }
