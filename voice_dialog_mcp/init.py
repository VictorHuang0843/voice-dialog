"""init: guided bootstrap for first-time users.

顺序执行并输出人类可读报告：
  1. uv         —— 没有：macOS 试 brew/curl 自动装，其他平台给命令
  2. ffmpeg     —— 可选（提示音+兜底录音），没有只警告
  3. uv sync    —— 装全部 Python 依赖（自动下载匹配的 Python）
  4. whisper 模型 —— 预下载（--skip-model 跳过，首次 listen 也会自动下）
  5. 麦克风探针 —— 1 秒实录，专抓 macOS TCC / Windows 隐私权限
  6. TTS 探针   —— 出声即通过
  7. MCP 注册   —— 打印 claude mcp add 命令（带本项目真实路径）
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

from . import platform as P

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OS = platform.system()


def _log(msg: str) -> None:
    print(f"[voice-dialog] {msg}", file=sys.stderr, flush=True)


def _say(line: str) -> None:
    print(line, flush=True)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 600), **kw)


# ---------------------------------------------------------------- steps ----
def ensure_uv() -> dict:
    if shutil.which("uv"):
        return {"ok": True, "detail": shutil.which("uv")}
    if OS == "Darwin":
        if shutil.which("brew"):
            _say("  uv 未安装，尝试 brew install uv ...")
            r = _run(["brew", "install", "uv"], timeout=1200)
            if r.returncode == 0 and shutil.which("uv"):
                return {"ok": True, "detail": "installed via brew"}
            return {"ok": False, "detail": "brew install uv 失败：" + r.stderr[-200:]}
        _say("  无 brew，尝试官方脚本安装 uv ...")
        r = _run(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], timeout=600)
        if r.returncode == 0:
            # 脚本装到 ~/.local/bin，补 PATH 提示
            return {"ok": True, "detail": "installed via astral.sh script（新终端或 "
                    "export PATH=\"$HOME/.local/bin:$PATH\" 生效）"}
        return {"ok": False, "detail": "官方脚本失败；手动执行: curl -LsSf https://astral.sh/uv/install.sh | sh"}
    if OS == "Windows":
        return {"ok": False, "detail": "手动安装: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""}
    return {"ok": False, "detail": "手动安装: curl -LsSf https://astral.sh/uv/install.sh | sh"}


def ensure_ffmpeg() -> dict:
    if P.ffmpeg_path():
        return {"ok": True, "detail": P.ffmpeg_path(), "optional": True}
    hint = {
        "Darwin": "brew install ffmpeg",
        "Windows": "winget install ffmpeg",
        "Linux": "sudo apt install ffmpeg  # 或 dnf install ffmpeg",
    }.get(OS, "")
    return {"ok": False, "detail": f"未安装（可选，缺了没有提示音/兜底录音）。安装: {hint}", "optional": True}


def ensure_deps() -> dict:
    _say("  uv sync（首次会自动下载匹配的 Python，约 30~60 秒）...")
    r = _run(["uv", "sync"], cwd=PROJECT_ROOT, timeout=1200)
    if r.returncode == 0:
        return {"ok": True, "detail": "dependencies installed"}
    return {"ok": False, "detail": r.stderr[-300:]}


def warm_model() -> dict:
    _say("  预下载 whisper 模型 small（~464MB，国内自动走 hf-mirror，可能几分钟）...")
    try:
        from .asr import get_model
        get_model()
        return {"ok": True, "detail": "model cached and loadable"}
    except Exception as exc:
        return {"ok": False, "detail": f"{exc}；可 export HF_ENDPOINT=https://hf-mirror.com 后重试"}


def probe_mic() -> dict:
    try:
        from .recorder import record_fixed
        rec = record_fixed(1.0)
        peak = max(abs(b) for b in rec["pcm"][:4000]) if rec["pcm"] else 0
        return {"ok": True, "detail": f"录音正常（1s, peak={peak}）"}
    except Exception as exc:
        return {"ok": False, "detail": f"{exc} —— 请在系统设置里给终端/宿主 App 麦克风权限"}


def probe_tts() -> dict:
    try:
        P.tts_speak("初始化完成，语音输出正常。", lang_hint="zh")
        return {"ok": True, "detail": "spoken ok"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def mcp_hint() -> dict:
    cmd = (f"claude mcp add voice-dialog -s user -- "
           f"uv --project {PROJECT_ROOT} run voice-dialog serve")
    return {"ok": True, "detail": f"Claude Code 用户执行: {cmd}"}


# ------------------------------------------------------------------ run ----
def run(skip_model: bool = False) -> dict:
    report: dict = {"project_root": PROJECT_ROOT, "steps": {}}
    _say("== voice-dialog init ==")
    for key, fn, optional in [
        ("1/7 uv", ensure_uv, False),
        ("2/7 ffmpeg", ensure_ffmpeg, True),
        ("3/7 deps", ensure_deps, False),
        ("4/7 model", (lambda: {"ok": True, "detail": "skipped"}) if skip_model else warm_model, False),
        ("5/7 mic", probe_mic, False),
        ("6/7 tts", probe_tts, False),
        ("7/7 mcp", mcp_hint, True),
    ]:
        _say(f"[{key}]")
        try:
            report["steps"][key] = fn()
        except Exception as exc:
            report["steps"][key] = {"ok": False, "detail": str(exc), "optional": optional}
        _say("  -> " + ("OK" if report["steps"][key]["ok"] else "FAIL") + ": "
             + report["steps"][key]["detail"][:200])
        # 硬前置失败直接短路，后面步骤没有意义
        if not report["steps"][key]["ok"] and not optional and key != "4/7 model":
            report["ready"] = False
            _say("init 未完成：修好上面的 FAIL 再跑一次 `voice-dialog init`。")
            return report
    hard_ok = all(v["ok"] for k, v in report["steps"].items()
                  if k != "4/7 model" and not v.get("optional"))
    model_ok = report["steps"]["4/7 model"]["ok"]
    report["ready"] = hard_ok
    _say(f"init {'完成' if hard_ok else '未完成'}"
         + ("（模型已就绪）" if model_ok else "（模型未下载，首次 listen 自动补）"))
    return report
