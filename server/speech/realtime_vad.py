import math
import os
import wave
from io import BytesIO
from typing import Dict, List, Optional, Tuple


PCM_SAMPLE_RATE = max(8000, int(os.getenv("STT_WS_PCM_SAMPLE_RATE", "16000")))
VAD_START_RMS = float(os.getenv("STT_WS_VAD_START_RMS", "0.014"))
VAD_END_RMS = float(os.getenv("STT_WS_VAD_END_RMS", "0.009"))
VAD_START_HOLD = max(1, int(os.getenv("STT_WS_VAD_START_HOLD_FRAMES", "2")))
VAD_END_HOLD = max(1, int(os.getenv("STT_WS_VAD_END_HOLD_FRAMES", "3")))
MIN_SPEECH_MS = max(80, int(os.getenv("STT_WS_MIN_SPEECH_MS", "240")))
MAX_SPEECH_MS = max(1200, int(os.getenv("STT_WS_MAX_SPEECH_MS", "12000")))
MIN_PCM_BYTES = max(320, int(os.getenv("STT_WS_MIN_PCM_BYTES", "640")))


class RealtimePcmVadSession:
    def __init__(self) -> None:
        self.in_speech = False
        self.start_hits = 0
        self.end_hits = 0
        self.speech_chunks: List[bytes] = []
        self.trailing_silence_chunks: List[bytes] = []
        self.segment_samples = 0
        self.min_samples = int(PCM_SAMPLE_RATE * (MIN_SPEECH_MS / 1000.0))
        self.max_samples = int(PCM_SAMPLE_RATE * (MAX_SPEECH_MS / 1000.0))

    def reset(self) -> None:
        self.in_speech = False
        self.start_hits = 0
        self.end_hits = 0
        self.speech_chunks = []
        self.trailing_silence_chunks = []
        self.segment_samples = 0

    def accept_pcm_chunk(self, pcm_bytes: bytes) -> Tuple[List[Dict[str, object]], List[bytes]]:
        chunk = _normalize_pcm16le_chunk(pcm_bytes)
        if not chunk:
            return [], []

        rms = _chunk_rms(chunk)
        events: List[Dict[str, object]] = []
        segments: List[bytes] = []

        if not self.in_speech:
            if rms >= VAD_START_RMS:
                self.start_hits += 1
            else:
                self.start_hits = 0

            if self.start_hits >= VAD_START_HOLD:
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

        if rms < VAD_END_RMS:
            self.end_hits += 1
            self.trailing_silence_chunks.append(chunk)
        else:
            self.end_hits = 0
            self.trailing_silence_chunks = []

        should_close = False
        if self.end_hits >= VAD_END_HOLD:
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

    def flush(self) -> Tuple[List[Dict[str, object]], List[bytes]]:
        if not self.in_speech:
            return [], []
        segment = self._finalize_segment_bytes()
        events = [{"type": "speech_end"}]
        return events, ([segment] if segment is not None else [])

    def _finalize_segment_bytes(self) -> Optional[bytes]:
        raw = b"".join(self.speech_chunks)
        sample_count = len(raw) // 2
        self.reset()
        if sample_count < self.min_samples:
            return None
        return _pcm16le_to_wav_bytes(raw, PCM_SAMPLE_RATE)


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
        value = int.from_bytes(pcm_bytes[i : i + 2], byteorder="little", signed=True)
        sample = float(value) / 32768.0
        total += sample * sample
    return math.sqrt(total / samples)


def _pcm16le_to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
    with BytesIO() as buf:
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()
