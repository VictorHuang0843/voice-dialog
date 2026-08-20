"""Local ASR: lazy faster-whisper, HF-mirror fallback, language auto-detect."""
from __future__ import annotations

import os

import sys
from functools import lru_cache

MODEL_SIZE = os.environ.get("VD_MODEL", "small")
# auto = detect per-utterance (whisper handles ~100 languages); pin e.g. VD_LANG=zh
LANG = os.environ.get("VD_LANG") or None  # None -> auto


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


@lru_cache(maxsize=1)
def get_model():
    """Load (and if necessary download) the whisper model once per process."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run: uv add faster-whisper "
            "(or pip install faster-whisper)"
        ) from exc

    for attempt, endpoint in enumerate(["primary", "mirror"]):
        if endpoint == "mirror":
            # CN networks often can't reach huggingface.co directly.
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        try:
            _log(f"loading whisper '{MODEL_SIZE}' (attempt {attempt + 1})...")
            model = WhisperModel(MODEL_SIZE, device="auto", compute_type="int8")
            # Force the actual download now so failures surface here, not mid-call.
            from huggingface_hub import scan_cache_dir
            scan_cache_dir()  # no-op warm check; real download happens below
            _ = model.transcribe.__doc__  # attribute touch; model is constructed lazily-safe
            return model
        except Exception as exc:
            _log(f"model load attempt {attempt + 1} failed: {exc}")
    raise RuntimeError(
        f"could not load whisper model '{MODEL_SIZE}' from HF or mirror; "
        "check network or pre-download manually"
    )


def transcribe(pcm: bytes, wav_path: str | None = None) -> dict:
    """Transcribe 16kHz mono 16-bit PCM. Returns {text, lang, confidence, low_confidence}."""
    import numpy as np

    model = get_model()
    audio = np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0
    segments, info = model.transcribe(
        audio,
        language=LANG,
        beam_size=1,
        vad_filter=True,          # trims leading/trailing silence at the ASR layer too
        without_timestamps=True,
    )
    seg_list = list(segments)
    text = "".join(seg.text for seg in seg_list).strip()
    # Speech coverage: share of audio whisper classified as speech. Clean speech
    # ~0.6+; noise/garbage < 0.25. (faster-whisper exposes no word confidence.)
    coverage = (
        sum(seg.end - seg.start for seg in seg_list) / info.duration
        if info.duration > 0.3 else 0.0
    )
    low = (not text) or coverage < 0.25
    return {
        "text": text,
        "lang": info.language,
        "confidence": round(min(coverage, 1.0), 3),
        "low_confidence": low,
    }
