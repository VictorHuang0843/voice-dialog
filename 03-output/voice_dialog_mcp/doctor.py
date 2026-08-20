"""doctor: one-shot environment report. Also a CLI subcommand for humans."""
from __future__ import annotations

import os
import platform
import shutil
import sys

from . import platform as P
from .asr import LANG, MODEL_SIZE


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


def run(probe_mic: bool = True) -> dict:
    report: dict = {"os": f"{platform.system()} {platform.release()}", "items": {}}
    items = report["items"]

    # ffmpeg (fallback recorder + beeps)
    ff = P.ffmpeg_path()
    items["ffmpeg"] = {"ok": bool(ff), "detail": ff or "not found (brew install ffmpeg / winget install ffmpeg)"}

    # microphone via PortAudio
    mics = []
    try:
        import sounddevice as sd
        mics = [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        items["microphones"] = {"ok": len(mics) > 0, "detail": "; ".join(mics[:3]) or "no input device"}
    except Exception as exc:
        items["microphones"] = {"ok": False, "detail": f"PortAudio error: {exc}"}

    # TTS
    tts = "unknown"
    if P.OS == "Darwin":
        tts = "macOS `say` (built-in)"
    elif P.OS == "Windows":
        tts = "Windows SAPI (built-in)"
    else:
        tts = next((c for c in ("espeak-ng", "espeak", "flite") if shutil.which(c)), "NOT FOUND — install espeak-ng")
    items["tts"] = {"ok": not tts.startswith("NOT"), "detail": tts}

    # whisper model
    model_item = {"ok": False, "detail": f"{MODEL_SIZE} (lang={LANG or 'auto'})"}
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    if os.path.isdir(cache) and any(MODEL_SIZE in d for d in os.listdir(cache)):
        model_item = {"ok": True, "detail": f"{MODEL_SIZE} cached (lang={LANG or 'auto'})"}
    else:
        model_item["detail"] += " — will download on first listen (HF_ENDPOINT mirror fallback applies)"
    items["whisper_model"] = model_item

    # real 1s recording probe: only way to catch TCC/privacy denials
    if probe_mic and mics:
        try:
            from .recorder import record_fixed
            probe = record_fixed(1.0)
            peak = max(abs(b) for b in probe["pcm"][:4000]) if probe["pcm"] else 0
            items["mic_probe"] = {
                "ok": True,
                "detail": f"recorded 1s, peak amplitude {peak} "
                          f"({'silence' if peak < 300 else 'sound detected'})",
            }
        except Exception as exc:
            items["mic_probe"] = {"ok": False, "detail": f"{exc} — grant mic permission to your terminal"}
    elif probe_mic:
        items["mic_probe"] = {"ok": False, "detail": "skipped: no input device"}

    report["ready"] = all(v["ok"] for k, v in items.items() if k != "whisper_model") and (
        items["whisper_model"]["ok"] or True  # model lazily downloads later
    )
    return report
