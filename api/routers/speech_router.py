import logging
import math
import os
from io import BytesIO
import time
import wave
from typing import Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response as FastAPIResponse

from api.routers.schemas import TTSRequest
from services.speech_service import detect_audio_media_type, speech_to_text, text_to_speech

router = APIRouter(tags=["speech"])

WS_STT_PCM_SAMPLE_RATE = max(8000, int(os.getenv("STT_WS_PCM_SAMPLE_RATE", "16000")))
WS_STT_VAD_START_RMS = float(os.getenv("STT_WS_VAD_START_RMS", "0.014"))
WS_STT_VAD_END_RMS = float(os.getenv("STT_WS_VAD_END_RMS", "0.009"))
WS_STT_VAD_START_HOLD_FRAMES = max(1, int(os.getenv("STT_WS_VAD_START_HOLD_FRAMES", "2")))
WS_STT_VAD_END_HOLD_FRAMES = max(1, int(os.getenv("STT_WS_VAD_END_HOLD_FRAMES", "3")))
WS_STT_MIN_SPEECH_MS = max(80, int(os.getenv("STT_WS_MIN_SPEECH_MS", "240")))
WS_STT_MAX_SPEECH_MS = max(1200, int(os.getenv("STT_WS_MAX_SPEECH_MS", "12000")))
WS_STT_MIN_PCM_BYTES = max(320, int(os.getenv("STT_WS_MIN_PCM_BYTES", "640")))


class _RealtimePcmVadSession:
    def __init__(self) -> None:
        self.in_speech = False
        self.start_hits = 0
        self.end_hits = 0
        self.speech_chunks: list[bytes] = []
        self.trailing_silence_chunks: list[bytes] = []
        self.segment_samples = 0
        self.min_samples = int(WS_STT_PCM_SAMPLE_RATE * (WS_STT_MIN_SPEECH_MS / 1000.0))
        self.max_samples = int(WS_STT_PCM_SAMPLE_RATE * (WS_STT_MAX_SPEECH_MS / 1000.0))

    def reset(self) -> None:
        self.in_speech = False
        self.start_hits = 0
        self.end_hits = 0
        self.speech_chunks = []
        self.trailing_silence_chunks = []
        self.segment_samples = 0

    def accept_pcm_chunk(self, pcm_bytes: bytes) -> tuple[list[Dict[str, object]], list[bytes]]:
        chunk = _normalize_pcm16le_chunk(pcm_bytes)
        if not chunk:
            return [], []

        rms = _chunk_rms(chunk)
        events: list[Dict[str, object]] = []
        segments: list[bytes] = []

        if not self.in_speech:
            if rms >= WS_STT_VAD_START_RMS:
                self.start_hits += 1
            else:
                self.start_hits = 0

            if self.start_hits >= WS_STT_VAD_START_HOLD_FRAMES:
                self.in_speech = True
                self.start_hits = 0
                self.end_hits = 0
                self.speech_chunks = [chunk]
                self.trailing_silence_chunks = []
                self.segment_samples = len(chunk) // 2
                events.append({"type": "speech_start"})
            return events, segments

        self.speech_chunks.append(chunk)
        self.segment_samples += len(chunk) // 2

        if rms < WS_STT_VAD_END_RMS:
            self.end_hits += 1
            self.trailing_silence_chunks.append(chunk)
        else:
            self.end_hits = 0
            self.trailing_silence_chunks = []

        should_close = False
        if self.end_hits >= WS_STT_VAD_END_HOLD_FRAMES:
            should_close = True
            if self.trailing_silence_chunks:
                silence_samples = sum(len(x) // 2 for x in self.trailing_silence_chunks)
                keep_count = max(0, len(self.speech_chunks) - len(self.trailing_silence_chunks))
                self.speech_chunks = self.speech_chunks[:keep_count]
                self.segment_samples = max(0, self.segment_samples - silence_samples)
        elif self.segment_samples >= self.max_samples:
            should_close = True

        if should_close:
            segment = self._finalize_segment_bytes()
            events.append({"type": "speech_end"})
            if segment is not None:
                segments.append(segment)
        return events, segments

    def flush(self) -> tuple[list[Dict[str, object]], list[bytes]]:
        if not self.in_speech:
            return [], []
        segment = self._finalize_segment_bytes()
        events = [{"type": "speech_end"}]
        return events, ([segment] if segment is not None else [])

    def _finalize_segment_bytes(self) -> bytes | None:
        raw = b"".join(self.speech_chunks)
        sample_count = len(raw) // 2
        self.reset()
        if sample_count < self.min_samples:
            return None
        return _pcm16le_to_wav_bytes(raw, WS_STT_PCM_SAMPLE_RATE)


def _normalize_pcm16le_chunk(pcm_bytes: bytes) -> bytes:
    if not pcm_bytes:
        return b""
    n = len(pcm_bytes)
    if n < 2:
        return b""
    if n % 2 == 1:
        return pcm_bytes[:-1]
    return pcm_bytes


def _chunk_rms(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return 0.0
    samples = int(len(pcm_bytes) / 2)
    if samples <= 0:
        return 0.0
    total = 0.0
    for i in range(0, len(pcm_bytes), 2):
        v = int.from_bytes(pcm_bytes[i : i + 2], byteorder="little", signed=True)
        f = float(v) / 32768.0
        total += f * f
    return math.sqrt(total / samples)


def _pcm16le_to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
    with BytesIO() as buf:
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()


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
    session = _RealtimePcmVadSession()
    await websocket.send_json(
        {
            "type": "ready",
            "detail": "stt websocket ready",
            "sample_rate": WS_STT_PCM_SAMPLE_RATE,
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
            if payload_bytes is None or len(payload_bytes) < WS_STT_MIN_PCM_BYTES:
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
