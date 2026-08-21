"""voice-dialog-mcp: MCP server + CLI in one entry point.

MCP tools: speak / listen / ask_by_voice / doctor
CLI:       voice-dialog speak "text" | listen | ask "text" | doctor

The single-round rule: ask_by_voice plays one utterance and listens once.
It NEVER auto-continues into another round — follow-ups are agent logic.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import platform as P
from .asr import transcribe
from .doctor import run as doctor_run
from .init import run as init_run
from .recorder import record_with_vad


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


# ------------------------------------------------------------- actions ----
def do_speak(text: str, lang: str | None = None, volume: int = 0) -> dict:
    if not text.strip():
        return {"ok": False, "error": "empty text"}
    P.tts_speak(text, lang_hint=lang, volume=volume)
    return {"ok": True, "spoken": text}


def do_listen(
    *,
    wait_start: float = 30.0,
    silence: float = 3.0,
    max_len: float = 60.0,
    device: int | None = None,
    lang: str | None = None,
) -> dict:
    rec = record_with_vad(wait_start=wait_start, silence=silence,
                          max_len=max_len, device=device)
    if rec["status"] == "no_speech":
        return {"ok": True, "no_speech": True, "text": "", "note": "nothing was said"}
    result = transcribe(rec["pcm"])
    result["ok"] = True
    result["no_speech"] = False
    return result


def do_ask(
    text: str,
    *,
    wait_start: float = 30.0,
    silence: float = 3.0,
    max_len: float = 60.0,
    device: int | None = None,
    lang: str | None = None,
    volume: int = 0,
) -> dict:
    """One atomic round: speak -> wait -> listen once. Returns transcript."""
    do_speak(text, lang=lang, volume=volume)
    return do_listen(wait_start=wait_start, silence=silence, max_len=max_len,
                     device=device, lang=lang)


# ---------------------------------------------------------------- MCP ----
def serve() -> None:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent, Tool

    app = Server("voice-dialog-mcp")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="speak",
                description=(
                    "Speak text aloud via local TTS and return when playback "
                    "finishes. For final/one-way announcements. Do not use for "
                    "questions — use ask_by_voice."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "lang": {"type": "string", "description": "ISO hint like zh/en; omit for auto"},
                        "volume": {"type": "integer", "minimum": 0, "maximum": 100,
                                   "description": "set output volume % before speaking; 0 = leave as-is"},
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="listen",
                description=(
                    "Record with voice-activity detection until the user is "
                    "silent for 5s, then transcribe locally. Use when the agent "
                    "expects the user to dictate. Returns transcript text; "
                    "no_speech=true means nobody talked within wait_start."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "wait_start": {"type": "number", "default": 30,
                                       "description": "max seconds to wait for speech to begin"},
                        "silence": {"type": "number", "default": 3,
                                    "description": "trailing silence seconds that end the utterance"},
                        "max_len": {"type": "number", "default": 60},
                        "lang": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="ask_by_voice",
                description=(
                    "Atomic one-round voice dialog: speak the question, then "
                    "listen once (3s-silence endpointing), return the user's "
                    "transcribed answer. NEVER chains into further rounds — "
                    "call again explicitly if you need another round. Raise "
                    "wait_start for slow physical actions (e.g. 600 for QR scans)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "question to speak"},
                        "wait_start": {"type": "number", "default": 30},
                        "silence": {"type": "number", "default": 5},
                        "max_len": {"type": "number", "default": 60},
                        "lang": {"type": "string"},
                        "volume": {"type": "integer", "minimum": 0, "maximum": 100, "default": 0},
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="init",
                description=(
                    "Guided bootstrap for first use: installs uv (macOS auto), "
                    "python deps via uv sync, pre-downloads the whisper model, "
                    "probes mic permission and TTS with a real test. Run this "
                    "when voice tools fail on a fresh machine; safe to re-run."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skip_model": {"type": "boolean", "default": False},
                    },
                },
            ),
            Tool(
                name="doctor",
                description=(
                    "Check environment health: ffmpeg, microphones, TTS engine, "
                    "whisper model, and a real 1-second mic permission probe. "
                    "Run this first when voice tools misbehave."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "speak":
                result = do_speak(arguments["text"], lang=arguments.get("lang"),
                                  volume=arguments.get("volume", 0))
            elif name == "listen":
                result = do_listen(
                    wait_start=arguments.get("wait_start", 30.0),
                    silence=arguments.get("silence", 3.0),
                    max_len=arguments.get("max_len", 60.0),
                    lang=arguments.get("lang"),
                )
            elif name == "ask_by_voice":
                result = do_ask(
                    arguments["text"],
                    wait_start=arguments.get("wait_start", 30.0),
                    silence=arguments.get("silence", 3.0),
                    max_len=arguments.get("max_len", 60.0),
                    lang=arguments.get("lang"),
                    volume=arguments.get("volume", 0),
                )
            elif name == "init":
                result = init_run(skip_model=arguments.get("skip_model", False))
            elif name == "doctor":
                result = doctor_run(probe_mic=True)
            else:
                result = {"ok": False, "error": f"unknown tool {name}"}
        except Exception as exc:
            _log(f"tool {name} failed: {exc}")
            result = {"ok": False, "error": str(exc)}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    import anyio

    async def main() -> None:
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    anyio.run(main)


# ---------------------------------------------------------------- CLI ----
def cli() -> None:
    ap = argparse.ArgumentParser(prog="voice-dialog")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("speak", help="speak text aloud")
    s.add_argument("text")
    s.add_argument("--lang")
    s.add_argument("--volume", type=int, default=0)

    l = sub.add_parser("listen", help="record + transcribe once")
    l.add_argument("--wait-start", type=float, default=30.0)
    l.add_argument("--silence", type=float, default=5.0)
    l.add_argument("--max-len", type=float, default=60.0)
    l.add_argument("--lang")

    a = sub.add_parser("ask", help="speak text then listen once")
    a.add_argument("text")
    a.add_argument("--wait-start", type=float, default=30.0)
    a.add_argument("--silence", type=float, default=5.0)
    a.add_argument("--max-len", type=float, default=60.0)
    a.add_argument("--lang")
    a.add_argument("--volume", type=int, default=0)

    sub.add_parser("doctor", help="environment health check")

    i = sub.add_parser("init", help="guided bootstrap: uv/ffmpeg/deps/model/mic/tts")
    i.add_argument("--skip-model", action="store_true", help="skip whisper pre-download")
    sub.add_parser("serve", help="run as MCP stdio server")

    ns = ap.parse_args()
    if ns.cmd == "serve":
        serve()
    elif ns.cmd == "speak":
        print(json.dumps(do_speak(ns.text, lang=ns.lang, volume=ns.volume), ensure_ascii=False))
    elif ns.cmd == "listen":
        print(json.dumps(do_listen(wait_start=ns.wait_start, silence=ns.silence,
                                   max_len=ns.max_len, lang=ns.lang), ensure_ascii=False))
    elif ns.cmd == "ask":
        print(json.dumps(do_ask(ns.text, wait_start=ns.wait_start, silence=ns.silence,
                                max_len=ns.max_len, lang=ns.lang, volume=ns.volume),
                         ensure_ascii=False))
    elif ns.cmd == "doctor":
        print(json.dumps(doctor_run(probe_mic=True), ensure_ascii=False, indent=2))
    elif ns.cmd == "init":
        init_run(skip_model=ns.skip_model)


if __name__ == "__main__":
    cli()
