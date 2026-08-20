"""Platform adapter: the ONLY module that knows about OS differences.

Exposes: record_cmd(), tts_speak(), beep(), open_default(). Everything else in the
package talks to these primitives, never to the OS directly.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import wave

OS = platform.system()  # 'Darwin' | 'Windows' | 'Linux'


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- record ----
# sounddevice/PortAudio records natively on all platforms; ffmpeg is only a
# fallback for devices PortAudio can't open. Default path = sounddevice.


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


# ------------------------------------------------------------------- tts ----
def tts_speak(text: str, lang_hint: str | None = None, volume: int = 70) -> None:
    """Speak text via the platform's native TTS. Blocking: returns after playback.

    volume: 0-100 output volume to set before speaking (0 = leave as-is).
    lang_hint: ISO code like 'zh'/'en'; used to pick a voice when supported.
    """
    if volume > 0:
        _set_volume(volume)

    if OS == "Darwin":
        _speak_macos(text, lang_hint)
    elif OS == "Windows":
        _speak_windows(text, lang_hint)
    else:
        _speak_linux(text)


def _set_volume(volume: int) -> None:
    try:
        if OS == "Darwin":
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {min(volume, 100)}"],
                timeout=5, check=False,
            )
        elif OS == "Windows":
            # nircmd not assumed; PowerShell SendKeys to master volume is flaky.
            # SAPI volume is controlled per-utterance instead.
            pass
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{min(volume, 100)}%"],
                           timeout=5, check=False)
    except Exception as exc:  # volume is best-effort, never fatal
        _log(f"set volume failed (ignored): {exc}")


def _macos_voice(lang_hint: str | None) -> str | None:
    """Pick a zh/en voice from installed macOS voices. Cached per-process."""
    global _MACOS_VOICE_CACHE
    if _MACOS_VOICE_CACHE is not None:
        return _MACOS_VOICE_CACHE
    want = "zh" if (lang_hint or "").lower().startswith("zh") else None
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10)
        voices = out.stdout.splitlines()
    except Exception:
        voices = []
    chosen = None
    if want:
        # Prefer quality voices (Tingting) over novelty ones (Eddy/Flo/...):
        # `say -v ?` lists them interleaved and Eddy sorts first on zh_CN.
        preferred = [n for n in ("Tingting", "Meijia", "Sinji", "Li-mu")
                     if any(l.startswith(n) for l in voices)]
        if preferred:
            chosen = preferred[0]
    if not chosen:
        for line in voices:
            # format: "Name (locale)  code  # greeting"
            if want and f"({want}" in line:
                chosen = line.split()[0]
                break
    if not chosen and want:  # any Chinese voice at all
        for line in voices:
            if "zh" in line.split("#")[0]:
                chosen = line.split()[0]
                break
    _MACOS_VOICE_CACHE = chosen  # None = let `say` pick the default
    return chosen


_MACOS_VOICE_CACHE: str | None = None


def _speak_macos(text: str, lang_hint: str | None) -> None:
    voice = _macos_voice(lang_hint)
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    _run_text_safe(cmd, text)


def _speak_windows(text: str, lang_hint: str | None) -> None:
    # PS 5.1 on CN-Windows decodes BOM-less UTF-8 as GBK, so the utterance MUST
    # travel via a UTF-8 file, never via an inline command argument.
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8-sig") as f:
        f.write(text)
        path = f.name
    lang_map = {"zh": "zh-CN", "en": "en-US"}
    culture = lang_map.get((lang_hint or "")[:2].lower(), "")
    ps = "$t=[IO.File]::ReadAllText($env:VD_TEXT,[Text.Encoding]::UTF8);"
    ps += "$s=New-Object -ComObject SAPI.SpVoice;"
    if culture:
        # Ask SAPI to prefer a voice matching the culture; fall back silently.
        ps += (
            "foreach($v in $s.GetVoices()){"
            f"if($v.GetAttribute('Language') -like '{culture.replace('-', '')}*')"
            "-or $v.GetDescription() -match '{culture}'){ $s.SelectVoice($v.GetDescription()); break }};"
        )
    ps += "$s.Rate=0;$s.Speak($t)|Out-Null"
    env = {**os.environ, "VD_TEXT": path}
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=env, timeout=300, check=False,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _speak_linux(text: str) -> None:
    # No universal native TTS; try common local engines in order, text via
    # stdin/file to dodge shell quoting.
    for cmd in (["say"], ["espeak-ng"], ["espeak"], ["flite"]):
        if shutil.which(cmd[0]):
            _run_text_safe(cmd, text)
            return
    _log("no TTS engine found on Linux (try: espeak-ng / speech-dispatcher)")


def _run_text_safe(cmd: list[str], text: str) -> None:
    """Run a TTS command, passing text via a UTF-8 temp file to avoid argv
    encoding/escaping issues on every platform."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        if cmd[0] == "say" and OS == "Darwin":
            subprocess.run(cmd + ["-f", path], timeout=300, check=False)
        elif cmd[0] in ("espeak-ng", "espeak"):
            subprocess.run(cmd + ["-f", path], timeout=300, check=False)
        else:
            subprocess.run(cmd, input=text.encode("utf-8"), timeout=300, check=False)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ------------------------------------------------------------------ beep ----
def beep(kind: str) -> None:
    """Play a short generated tone. kind: 'start' | 'end' | 'trunc'.

    Tones are synthesized by ffmpeg at runtime — zero bundled assets.
    """
    ff = ffmpeg_path()
    specs = {
        # (freq, duration, count) — rising pair = start, falling pair = end,
        # triple = truncated (user can hear the difference blind).
        "start": [(880, 0.12), (1320, 0.12)],
        "end": [(990, 0.12), (660, 0.16)],
        "trunc": [(740, 0.10), (740, 0.10), (740, 0.10)],
    }
    tones = specs.get(kind, specs["start"])
    if not ff:
        return  # silent degrade: no ffmpeg, no beeps, recording still works
    import subprocess
    import time as _time

    for freq, dur in tones:
        # Render with ffmpeg to a wav, then play with the platform default player.
        # Direct ffplay is NOT used on macOS: it picks its own core-audio device
        # (e.g. a BlackHole loopback) instead of the system default output, so
        # the user hears nothing even though ffmpeg reports success.
        import tempfile
        import os as _os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        try:
            # Step 1: render the tone with ffmpeg (only asset source needed).
            subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"sine=frequency={freq}:duration={dur}",
                            "-ar", "44100", wav],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False)
            if OS == "Darwin" and shutil.which("afplay"):
                player = ["afplay", wav]
            elif OS == "Windows" and shutil.which("powershell"):
                player = None  # rendered below via powershell SoundPlayer
            else:
                player = [ff.replace("ffmpeg", "ffplay"), "-nodisp", "-autoexit",
                          "-loglevel", "quiet", wav] if shutil.which(ff.replace("ffmpeg", "ffplay")) else None
            if OS == "Windows" and player is None:
                ps = ("(New-Object Media.SoundPlayer '" + wav + "').PlaySync();")
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False)
            elif player:
                subprocess.run(player, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5, check=False)
            else:
                # last resort: no player at all — skip silently
                pass
        finally:
            try:
                _os.unlink(wav)
            except OSError:
                pass
        _time.sleep(0.04)


# ---------------------------------------------------------------- audio ----
SR = 16000  # webrtcvad native rate; also faster-whisper's input rate — no resample


def write_wav(path: str, pcm: bytes) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def shell_record_async(out_wav: str, device: str | None, max_seconds: float) -> subprocess.Popen:
    """ffmpeg fallback recorder (used when PortAudio can't open the device)."""
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    if OS == "Darwin":
        input_spec = ["-f", "avfoundation", "-i", f":{device or '0'}"]
    elif OS == "Windows":
        input_spec = ["-f", "dshow", "-i", f"audio={device or '0'}"]
    else:
        input_spec = ["-f", "pulse", "-i", device or "default"]
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           *input_spec, "-t", str(max_seconds), "-ac", "1", "-ar", str(SR), out_wav]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
