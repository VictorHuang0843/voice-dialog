---
name: hcn-voice-dialog
description: Voice dialog with the user over local TTS + ASR (no cloud). Use when the user is away from the screen, at task completion, when a decision/input/approval is needed, or when the user asks to talk by voice. Tools come from the voice-dialog-mcp server (speak / listen / ask_by_voice / doctor); CLI fallback is `uv run voice-dialog <cmd>` from the voice-dialog project root.
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

## 初始化与自检

- **全新机器**：`voice-dialog init` —— 自动装 uv → 依赖 → 模型 → 权限/出声实测，FAIL 会给对应平台修复命令，可反复跑
- **日常体检**：`voice-dialog doctor`（只查不装）
- **skill 自检脚本**：`zsh scripts/health-check.zsh`（环境+发声+提示音+录音回环+总结五项）

## 环境变量

- `VD_LANG=zh|en|…` 钉死识别语言（默认 auto 检测）
- `VD_MODEL=small` 模型大小（tiny/base/small…，首次使用自动下载）

## CLI 兜底（MCP 不可用时）

```bash
cd /path/to/voice-dialog-mcp && uv run \
  voice-dialog ask "主人，测试一下？" --wait-start 60
```

## 调用纪律（踩过坑总结，必须遵守）

1. **每次语音播报必须走 MCP 工具或项目 CLI，禁止裸 `say`**——裸 say 只播不录，主人说话没人听。
2. **播报要收尾就接 listen/ask，不接就不要播**——"说完话开麦"是一个动作不是两个。
3. **CLI 命令必须在项目目录下执行**（cwd 重置后先 cd），且管道 grep 失败≠ask 失败，失败时看 stderr 别急着下结论。
4. 提示音语义：高亮上扬=开录，低沉下行=正常结束，急促三连=60秒截断。
