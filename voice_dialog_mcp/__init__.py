"""voice-dialog-mcp: local voice dialog primitives for any MCP-capable agent.

Design rules:
- ask_by_voice = one speak + one listen round. Never auto-continues.
- All inference is local (faster-whisper). VAD is pure signal processing (webrtcvad).
- Platform differences are confined to platform.py (record command strings, TTS, beep).
"""

__version__ = "0.1.0"
