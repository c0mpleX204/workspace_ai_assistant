import base64
import io
import os
import threading
import time
import wave
from array import array
from pathlib import Path

import requests

from config.config import settings
from .text_utils import should_drop_stt_text

_SHERPA_RECOGNIZER = None
_SHERPA_LOCK = threading.Lock()
_SHERPA_INIT_ERROR = None


def _resolve_sherpa_model_paths() -> tuple[Path, Path]:
    root_dir = str(getattr(settings, "local_stt_sherpa_model_dir", "") or "").strip()
    model_file_name = str(getattr(settings, "local_stt_sherpa_model_file", "model.int8.onnx") or "model.int8.onnx").strip()
    tokens_file_name = str(getattr(settings, "local_stt_sherpa_tokens_file", "tokens.txt") or "tokens.txt").strip()

    if not root_dir:
        raise RuntimeError(
            "未配置本地 sherpa-sense-voice 模型目录。"
            "请设置 LOCAL_STT_SHERPA_MODEL_DIR 指向包含 model.int8.onnx 和 tokens.txt 的目录。"
        )

    root = Path(root_dir)
    model_path = root / model_file_name
    tokens_path = root / tokens_file_name

    if not model_path.is_file() or not tokens_path.is_file():
        raise RuntimeError(
            "本地 sherpa-sense-voice 模型文件缺失。"
            f"期望文件: {model_path} 和 {tokens_path}"
        )

    return model_path, tokens_path


def _get_sherpa_recognizer():
    global _SHERPA_RECOGNIZER
    global _SHERPA_INIT_ERROR
    if _SHERPA_RECOGNIZER is not None:
        return _SHERPA_RECOGNIZER
    if _SHERPA_INIT_ERROR is not None:
        raise _SHERPA_INIT_ERROR

    with _SHERPA_LOCK:
        if _SHERPA_RECOGNIZER is not None:
            return _SHERPA_RECOGNIZER
        if _SHERPA_INIT_ERROR is not None:
            raise _SHERPA_INIT_ERROR

        try:
            import sherpa_onnx
        except Exception as exc:
            _SHERPA_INIT_ERROR = RuntimeError(
                "sherpa-onnx not available, please install and restart backend"
            )
            raise _SHERPA_INIT_ERROR from exc

        try:
            model_path, tokens_path = _resolve_sherpa_model_paths()
            _SHERPA_RECOGNIZER = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_path),
                tokens=str(tokens_path),
                num_threads=max(1, int(getattr(settings, "local_stt_sherpa_num_threads", 2))),
                sample_rate=max(8000, int(getattr(settings, "local_stt_sherpa_sample_rate", 16000))),
                provider=str(getattr(settings, "local_stt_sherpa_provider", "cpu") or "cpu"),
                language=str(getattr(settings, "local_stt_sherpa_language", "auto") or "auto"),
                use_itn=bool(getattr(settings, "local_stt_sherpa_use_itn", False)),
            )
            return _SHERPA_RECOGNIZER
        except Exception as exc:
            _SHERPA_INIT_ERROR = RuntimeError(f"本地 sherpa-sense-voice 初始化失败: {exc}")
            raise _SHERPA_INIT_ERROR


def _decode_pcm_frames(raw_frames: bytes, channel_count: int, sample_width: int) -> list[float]:
    if channel_count <= 0:
        raise RuntimeError("invalid wav channel count")

    if sample_width == 1:
        mono = [(x - 128) / 128.0 for x in raw_frames]
    elif sample_width == 2:
        pcm = array("h")
        pcm.frombytes(raw_frames)
        mono = [x / 32768.0 for x in pcm]
    elif sample_width == 4:
        pcm = array("i")
        pcm.frombytes(raw_frames)
        mono = [x / 2147483648.0 for x in pcm]
    else:
        raise RuntimeError(f"unsupported wav sample width: {sample_width}")

    if channel_count == 1:
        return mono

    downmixed: list[float] = []
    for i in range(0, len(mono), channel_count):
        frame = mono[i : i + channel_count]
        if frame:
            downmixed.append(sum(frame) / len(frame))
    return downmixed


def _resample(samples: list[float], in_rate: int, out_rate: int) -> list[float]:
    if not samples or in_rate == out_rate:
        return samples
    if len(samples) == 1:
        return samples[:]

    out_len = max(1, round(len(samples) * out_rate / in_rate))
    if out_len == 1:
        return [samples[0]]

    scale = (len(samples) - 1) / (out_len - 1)
    out: list[float] = []
    for i in range(out_len):
        pos = i * scale
        li = int(pos)
        ri = min(li + 1, len(samples) - 1)
        frac = pos - li
        out.append(samples[li] * (1.0 - frac) + samples[ri] * frac)
    return out


def _read_wav_samples(audio_bytes: bytes, target_sample_rate: int) -> list[float]:
    if not audio_bytes:
        return []
    with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frame_count = wf.getnframes()
        if frame_count <= 0:
            return []
        raw = wf.readframes(frame_count)

    samples = _decode_pcm_frames(raw, channels, width)
    return _resample(samples, sample_rate, target_sample_rate)


def _speech_to_text_local_sherpa_sense_voice(
    audio_bytes: bytes, filename: str = "audio.wav", language: str = "zh"
) -> str:
    _ = language
    suffix = str(filename or "").lower()
    if not suffix.endswith(".wav"):
        raise RuntimeError(
            "sherpa-sense-voice 本地识别当前仅支持 WAV 输入。"
            "请使用 /stt/ws 实时通道，或将 STT_PROVIDER 设为 remote_openai_compatible。"
        )

    sample_rate = max(8000, int(getattr(settings, "local_stt_sherpa_sample_rate", 16000)))
    samples = _read_wav_samples(audio_bytes, sample_rate)
    if not samples:
        return ""

    recognizer = _get_sherpa_recognizer()
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)

    result = stream.result
    text = str(getattr(result, "text", "") or "").strip()
    if should_drop_stt_text(text):
        return ""
    return text


def _speech_to_text_remote(
    audio_bytes: bytes, filename: str = "audio.webm", language: str = "zh"
) -> str:
    url = f"{settings.remote_primary_api_base_url.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.remote_primary_api_key}"}
    suffix = str(filename or "audio.webm").lower()
    if suffix.endswith(".wav"):
        content_type = "audio/wav"
    elif suffix.endswith(".mp3"):
        content_type = "audio/mpeg"
    elif suffix.endswith(".ogg"):
        content_type = "audio/ogg"
    else:
        content_type = "audio/webm"
    files = {"file": (filename, audio_bytes, content_type)}
    models = [settings.stt_model]
    fallback_model = str(getattr(settings, "stt_fallback_model", "") or "").strip()
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)

    attempts = max(0, int(getattr(settings, "stt_max_retries", 0))) + 1
    errors = []

    for model in models:
        data = {
            "model": model,
            "language": language,
            "response_format": "json",
        }

        last_error = None
        for idx in range(attempts):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=(10, settings.stt_timeout_sec),
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    snippet = (resp.text or "")[:200]
                    raise RuntimeError(f"stt upstream http {resp.status_code}: {snippet}")

                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "").strip()
            except requests.Timeout:
                last_error = RuntimeError(f"stt timeout after {settings.stt_timeout_sec}s")
            except requests.RequestException as exc:
                last_error = RuntimeError(f"stt request failed: {exc}")
            except Exception as exc:
                last_error = exc

            if idx < attempts - 1:
                time.sleep(0.6 * (idx + 1))

        errors.append(f"{model}: {last_error}")

    raise RuntimeError("stt failed across models: " + " | ".join(errors))


def speech_to_text(audio_bytes: bytes, filename: str = "audio.webm", language: str = "zh") -> str:
    provider = str(
        getattr(settings, "stt_provider", "sherpa_sense_voice") or "sherpa_sense_voice"
    ).lower()
    if provider in {"sherpa_sense_voice", "local_sherpa", "local"}:
        return _speech_to_text_local_sherpa_sense_voice(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
        )

    if provider in {"remote", "remote_openai_compatible", "openai_compatible"}:
        return _speech_to_text_remote(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
        )

    if provider in {"auto_remote_first", "auto"}:
        try:
            return _speech_to_text_remote(
                audio_bytes=audio_bytes,
                filename=filename,
                language=language,
            )
        except Exception:
            return _speech_to_text_local_sherpa_sense_voice(
                audio_bytes=audio_bytes,
                filename=filename,
                language=language,
            )

    if provider in {"auto_local_first"}:
        try:
            return _speech_to_text_local_sherpa_sense_voice(
                audio_bytes=audio_bytes,
                filename=filename,
                language=language,
            )
        except Exception:
            return _speech_to_text_remote(
                audio_bytes=audio_bytes,
                filename=filename,
                language=language,
            )

    raise RuntimeError(
        "未知 STT_PROVIDER。可用值：sherpa_sense_voice | remote_openai_compatible | auto_remote_first | auto_local_first"
    )


def _gpt_sovits_url() -> str:
    base = settings.local_gpt_sovits_base_url.rstrip("/")
    path = settings.local_gpt_sovits_tts_path
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _decode_base64_audio(audio_str: str) -> bytes:
    data = audio_str.strip()
    if data.startswith("data:"):
        sep = data.find(",")
        if sep != -1:
            data = data[sep + 1 :]
    return base64.b64decode(data)


def _tts_gpt_sovits_local(text: str, voice: str = "", speed: float = 1.0) -> bytes:
    url = _gpt_sovits_url()
    ref_audio_path = (
        voice.strip()
        if voice and ("/" in voice or "\\" in voice or ".wav" in voice.lower())
        else settings.local_gpt_sovits_ref_audio_path
    )
    payload = {
        "text": text,
        "text_lang": settings.local_gpt_sovits_text_lang,
        "prompt_text": settings.local_gpt_sovits_prompt_text,
        "prompt_lang": settings.local_gpt_sovits_prompt_lang,
        "ref_audio_path": ref_audio_path,
        "speed_factor": speed,
        "media_type": settings.local_gpt_sovits_media_type,
        "streaming_mode": False,
    }

    resp = requests.post(
        url,
        json=payload,
        timeout=(8, settings.local_gpt_sovits_timeout_sec),
    )
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "audio/" in content_type or "application/octet-stream" in content_type:
        return resp.content

    obj = resp.json()
    if isinstance(obj, dict):
        if isinstance(obj.get("audio"), str):
            return _decode_base64_audio(obj["audio"])
        if isinstance(obj.get("wav"), str):
            return _decode_base64_audio(obj["wav"])
        if isinstance(obj.get("output_path"), str):
            with open(obj["output_path"], "rb") as f:
                return f.read()

    raise RuntimeError(f"gpt-sovits local response unsupported: {str(obj)[:200]}")


def get_tts_media_type() -> str:
    provider = str(getattr(settings, "tts_provider", "siliconflow") or "siliconflow").lower()
    if provider == "gpt_sovits_local":
        media = (settings.local_gpt_sovits_media_type or "wav").lower()
        if media == "mp3":
            return "audio/mpeg"
        if media == "ogg":
            return "audio/ogg"
        return "audio/wav"
    return "audio/mpeg"


def detect_audio_media_type(audio_bytes: bytes) -> tuple[str, str]:
    if not audio_bytes:
        return "application/octet-stream", "bin"

    if len(audio_bytes) >= 12 and audio_bytes[0:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if audio_bytes.startswith(b"OggS"):
        return "audio/ogg", "ogg"
    if audio_bytes.startswith(b"ID3"):
        return "audio/mpeg", "mp3"
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return "audio/mpeg", "mp3"

    return "application/octet-stream", "bin"


def text_to_speech(text: str, voice: str = "", speed: float = 1.0) -> bytes:
    provider = str(getattr(settings, "tts_provider", "siliconflow") or "siliconflow").lower()
    if provider in {"gpt_sovits_local", "auto_local_first"}:
        try:
            return _tts_gpt_sovits_local(text=text, voice=voice, speed=speed)
        except Exception:
            if provider == "gpt_sovits_local":
                raise

    url = f"{settings.remote_primary_api_base_url.rstrip('/')}/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.remote_primary_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.tts_model,
        "input": text,
        "voice": voice or settings.tts_voice,
        "speed": speed,
        "response_format": "mp3",
    }
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=(10, settings.tts_timeout_sec),
    )
    resp.raise_for_status()
    return resp.content
