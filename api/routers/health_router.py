from typing import Dict

from fastapi import APIRouter, HTTPException

from config.config import settings
from services.model_service import warmup_model

router = APIRouter(tags=["health"])


@router.get("/health")
def api_health() -> Dict[str, object]:
    try:
        warm = warmup_model()
        return {
            "ok": True,
            "chat_model": settings.remote_primary_model,
            "stt_provider": settings.stt_provider,
            "stt_model": settings.stt_model,
            "local_stt_sherpa_model_dir": settings.local_stt_sherpa_model_dir,
            "local_stt_sherpa_provider": settings.local_stt_sherpa_provider,
            "local_stt_sherpa_sample_rate": settings.local_stt_sherpa_sample_rate,
            "tts_model": settings.tts_model,
            "tts_provider": settings.tts_provider,
            "warmup": warm,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"health check failed: {exc}")
