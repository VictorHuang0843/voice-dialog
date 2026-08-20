"""Recording loop: sounddevice stream + webrtcvad endpoint detection.

Sequence contract (heard by the user):
  beep('start') -> [wait up to `wait_start` for speech] -> record ->
  5s of silence -> beep('end') (or beep('trunc') at the hard cap).

No model involved in endpointing — webrtcvad is pure spectral signal processing.
"""
from __future__ import annotations

import sys

from . import platform as P

FRAME_MS = 30  # webrtcvad requires 10/20/30 ms frames
FRAME_SAMPLES = P.SR * FRAME_MS // 1000


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


def record_with_vad(
    *,
    wait_start: float = 30.0,   # max seconds to wait for the user to begin
    silence: float = 5.0,       # seconds of silence that ends the utterance
    max_len: float = 60.0,      # hard cap regardless of speech
    device: int | None = None,
    aggressiveness: int = 2,    # 0..3 webrtcvad
) -> dict:
    """Record until 5s of trailing silence. Returns {'pcm': bytes, 'status': str}.

    status: 'ok' | 'no_speech' | 'truncated'
    """
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)

    try:
        import sounddevice as sd
        stream_ctx = sd.InputStream(
            samplerate=P.SR, channels=1, dtype="int16",
            blocksize=FRAME_SAMPLES, device=device,
        )
    except Exception as exc:
        raise RuntimeError(
            f"cannot open microphone via PortAudio: {exc}. "
            "Check OS mic permission for your terminal, or run `doctor`."
        ) from exc

    pcm = bytearray()
    voiced_run = 0        # consecutive voiced frames while in-speech
    silence_run = 0.0     # trailing silence after speech started
    waiting = 0.0         # time with no speech yet
    speech_started = False
    trunc = False

    P.beep("start")

    with stream_ctx as stream:
        while True:
            frame, _ = stream.read(FRAME_SAMPLES)
            data = frame.tobytes()
            pcm += data
            is_speech = vad.is_speech(data, P.SR)

            if speech_started:
                if is_speech:
                    voiced_run += 1
                    silence_run = 0.0
                else:
                    silence_run += FRAME_MS / 1000
                    if silence_run >= silence:
                        break
            else:
                if is_speech:
                    speech_started = True
                    silence_run = 0.0
                else:
                    waiting += FRAME_MS / 1000
                    if waiting >= wait_start:
                        break
            if len(pcm) / (2 * P.SR) >= max_len:
                trunc = True
                break

    if not speech_started:
        P.beep("end")
        return {"pcm": b"", "status": "no_speech"}
    P.beep("trunc" if trunc else "end")
    return {"pcm": bytes(pcm), "status": "truncated" if trunc else "ok"}


def record_fixed(seconds: float, device: int | None = None) -> dict:
    """Fixed-length recording (doctor's permission probe — no VAD needed)."""
    import sounddevice as sd
    try:
        rec = sd.rec(int(seconds * P.SR), samplerate=P.SR, channels=1,
                     dtype="int16", device=device)
        sd.wait()
    except Exception as exc:
        raise RuntimeError(f"microphone probe failed: {exc}") from exc
    return {"pcm": rec.tobytes(), "status": "ok"}
