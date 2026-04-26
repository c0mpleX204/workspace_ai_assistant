import logging
import time
from typing import Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response as FastAPIResponse

from server.api.schemas import TTSRequest
from server.speech.realtime_vad import MIN_PCM_BYTES, PCM_SAMPLE_RATE, RealtimePcmVadSession
from server.services.speech_service import detect_audio_media_type, speech_to_text, text_to_speech

router = APIRouter(tags=["speech"])


@router.post("/stt")
async def api_stt(file: UploadFile = File(...)) -> Dict[str, str]:
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="音频文件为空")
        text = await run_in_threadpool(
            speech_to_text,
            audio_bytes,
            file.filename or "audio.webm",
        )
        return {"text": text}
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(
            f"stt failed filename={file.filename} size={len(audio_bytes) if 'audio_bytes' in locals() else 0}: {exc}"
        )
        raise HTTPException(status_code=500, detail=f"语音识别失败: {exc}")


@router.websocket("/stt/ws")
async def api_stt_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session = RealtimePcmVadSession()
    await websocket.send_json(
        {
            "type": "ready",
            "detail": "stt websocket ready",
            "sample_rate": PCM_SAMPLE_RATE,
        }
    )

    try:
        while True:
            message = await websocket.receive()
            event_type = message.get("type")
            if event_type == "websocket.disconnect":
                break

            payload_text = message.get("text")
            if payload_text is not None:
                cmd = str(payload_text).strip().lower()
                if cmd == "flush":
                    events, segments = session.flush()
                    for event in events:
                        await websocket.send_json(event)
                    for segment in segments:
                        try:
                            text = await run_in_threadpool(
                                speech_to_text,
                                segment,
                                f"vad-{int(time.time() * 1000)}.wav",
                            )
                            if text:
                                await websocket.send_json(
                                    {
                                        "type": "transcript",
                                        "text": text,
                                        "final": True,
                                    }
                                )
                        except Exception as exc:
                            logging.warning(f"stt ws flush transcribe failed: {exc}")
                    await websocket.send_json({"type": "flush_complete"})
                    continue
                if cmd == "reset":
                    session.reset()
                    await websocket.send_json({"type": "reset"})
                    continue
                continue

            payload_bytes = message.get("bytes")
            if payload_bytes is None or len(payload_bytes) < MIN_PCM_BYTES:
                continue

            try:
                events, segments = session.accept_pcm_chunk(payload_bytes)
                for event in events:
                    await websocket.send_json(event)
                for segment in segments:
                    text = await run_in_threadpool(
                        speech_to_text,
                        segment,
                        f"vad-{int(time.time() * 1000)}.wav",
                    )
                    if text:
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "text": text,
                                "final": True,
                            }
                        )
            except Exception as exc:
                logging.warning(f"stt ws chunk failed: {exc}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"语音识别失败: {exc}",
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logging.error(f"stt websocket failed: {exc}")


@router.post("/tts")
async def api_tts(payload: TTSRequest) -> FastAPIResponse:
    try:
        audio_bytes = await run_in_threadpool(
            text_to_speech,
            payload.text,
            payload.voice,
            payload.speed,
        )
        media_type, ext = detect_audio_media_type(audio_bytes)
        return FastAPIResponse(
            content=audio_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f"inline; filename=tts.{ext}"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音合成失败: {exc}")

