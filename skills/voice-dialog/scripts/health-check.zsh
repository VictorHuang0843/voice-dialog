#!/bin/zsh
# voice-dialog 自检/初始化。纯本地。
# 全新机器直接跑这个脚本即可（会自动引导安装）。
set -uo pipefail
PROJ="${VD_PROJECT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
cd "$PROJ" || exit 1

command -v uv >/dev/null || {
  echo "uv 未安装，先执行: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }

echo "== 1/5 依赖检查（新机器自动安装，旧机器秒过）=="
uv run voice-dialog init --skip-model 2>&1 | grep -E "OK|FAIL" | head -8

echo "== 2/5 TTS 发声（应听到说话）=="
uv run voice-dialog speak "自检：语音输出正常。" --lang zh >/dev/null 2>&1 && echo "speak: ok"

echo "== 3/5 提示音（高亮上扬=开录 / 低沉下行=结束）=="
uv run python -c "from voice_dialog_mcp.platform import beep; beep('start'); beep('end')" 2>/dev/null && echo "beep: ok"

echo "== 4/5 录音回环（叮响后说一句话，停3秒）=="
uv run voice-dialog listen --wait-start 30 2>/dev/null | grep -o '"text": "[^"]*"'

echo "== 5/5 doctor 总结 =="
uv run voice-dialog doctor 2>/dev/null | grep '"ready"'
echo "自检完成。"
