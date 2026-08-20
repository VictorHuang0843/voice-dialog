#!/bin/zsh
# voice-dialog 一键自检：环境 + 一次真实录音回环。纯本地。
# 用法: zsh health-check.zsh
set -uo pipefail
PROJ="/Users/victor/Documents/work/AI/2026-08-21--voice-dialog-mcp"
cd "$PROJ" || exit 1

echo "== 1/4 环境 doctor =="
uv run voice-dialog doctor | grep -E '"ready"|"ok"' | head -6

echo "== 2/4 TTS 发声（应听到说话）=="
uv run voice-dialog speak "自检：语音输出正常。" --lang zh >/dev/null 2>&1 && echo "speak: ok"

echo "== 3/4 提示音（应听到 叮 / 咚咚）=="
uv run python -c "from voice_dialog_mcp.platform import beep; beep('start'); beep('end')" 2>/dev/null && echo "beep: ok"

echo "== 4/4 录音回环（叮响后说一句话，停3秒）=="
uv run voice-dialog listen --wait-start 30 2>/dev/null | grep -o '"text": "[^"]*"'

echo "自检完成。四项都正常即可日常使用。"
