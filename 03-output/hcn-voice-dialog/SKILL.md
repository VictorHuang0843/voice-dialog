---
name: hcn-voice-dialog
description: Voice dialog with the user over local TTS + ASR (no cloud). Use when the user is away from the screen, at task completion, when a decision/input/approval is needed, or when the user asks to talk by voice. Tools come from the voice-dialog-mcp server (speak / listen / ask_by_voice / doctor); CLI fallback is `uv run --project /Users/victor/Documents/work/AI/2026-08-21--voice-dialog-mcp voice-dialog <cmd>`.
---

# 语音对话（本地 TTS + ASR）

## 何时用哪个工具

| 场景 | 工具 |
|---|---|
| 任务完成/里程碑播报（不需要回应） | `speak` |
| 需要主人决策、批准、或告知物理操作完成（如"扫完码了说一声"） | `ask_by_voice`（等待类场景调大 `wait_start`，扫码用 600） |
| 主人主动要求口述、连续补充指令 | `listen` |
| 声音工具行为异常、首次在新机器上 | `doctor` |

## 铁律（防死循环）

1. `ask_by_voice` = 说一句 + 听一次，**绝不自动续听**。要多轮必须自己显式再调。
2. 听到回答后**不复述原文**，把理解揉进下一步行动里播报："好，按稳定版来，我开始。"
3. 例外——**数字、金额、删除目标、文件路径**必须逐字复述确认后再动手。
4. `no_speech=true` 或 `low_confidence=true` 时可以重问，但**最多 2 次**，之后转文字等待并说明原因。
5. 播报内容要短（一两句），不念代码、不念密钥、不念验证码。

## 环境变量

- `VD_LANG=zh|en|…` 钉死识别语言（默认 auto 检测）
- `VD_MODEL=small` 模型大小（默认 small，已缓存在本机）

## CLI 兜底（MCP 不可用时）

```bash
uv run --project /Users/victor/Documents/work/AI/2026-08-21--voice-dialog-mcp \
  voice-dialog ask "主人，测试一下？" --wait-start 60
```
