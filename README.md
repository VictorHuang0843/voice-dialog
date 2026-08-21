# voice-dialog

**让任何 AI Agent 开口说话、竖耳倾听 —— 100% 本地，零云端依赖。**

一个 MCP server + CLI 双形态的语音对话工具。Agent 跑完任务语音播报、需要决策时语音提问、听你口述指令——识别用本地 whisper，合成用系统 TTS，端点检测用纯信号处理，你的语音数据不出电脑。

## 它能做什么

```
你（不看屏幕）："搞定了吗？"
Agent：🔊 "代码写完了，测试全绿。要提交吗？"     ← speak / ask_by_voice
你（在忙别的事）："先不提交，我看看再说"            ← 本地 whisper 听懂了
Agent：🔊 "好，代码留在工作区等你。"
```

| 工具 | 用途 |
|---|---|
| `speak` | 单向播报（任务完成、里程碑） |
| `listen` | 录音+识别（你口述指令） |
| `ask_by_voice` | 原子问答：说一句→听一次，绝不自动续听（防死循环） |
| `init` | 一键初始化（见下） |
| `doctor` | 环境体检（只查不装） |

## 快速开始

```bash
git clone https://github.com/VictorHuang0843/voice-dialog.git
cd voice-dialog

# 没装 uv？先来这个（Windows 用 install.ps1）：
#   curl -LsSf https://astral.sh/uv/install.sh | sh

uv run voice-dialog init
```

`init` 是 7 步全自动引导：装 uv → 装依赖（uv 连 Python 都帮你装好）→ 下载 whisper 模型（464MB，中国网络自动走 hf-mirror）→ 麦克风权限实测 → TTS 出声实测 → 打印 MCP 注册命令。哪步失败就给哪步的修复命令，修好重跑即可。

试一句：

```bash
uv run voice-dialog speak "语音系统就绪" --lang zh
uv run voice-dialog ask "请说话" --wait-start 60
# 你会听到：高亮上扬"叮↑"= 开始说话 → 停 3 秒 → 低沉"咚…咚↓"= 录音结束
```

## 接入你的 Agent

**任何 MCP 客户端**（Claude Code、Codex、Cursor、LoopX……）：

```json
{
  "mcpServers": {
    "voice-dialog": {
      "command": "uv",
      "args": ["--project", "/你的路径/voice-dialog", "run", "voice-dialog", "serve"]
    }
  }
}
```

**Claude Code 一行注册：**

```bash
claude mcp add voice-dialog -s user -- uv --project /你的路径/voice-dialog run voice-dialog serve
```

**不支持 MCP 的工具**：直接调 CLI，`uv run voice-dialog speak/listen/ask "..."`。

**Claude Code Skill**（可选，教 Agent 何时说/何时听）：把 `skills/voice-dialog/` 拷到 `~/.claude/skills/`。

## 支持的平台

| | macOS | Windows | Linux |
|---|---|---|---|
| 语音识别 | ✅ 已验收 | ✅ | ✅ |
| 语音合成 | ✅ 系统TTS | ✅ SAPI | ⚠️ 需装 espeak-ng |
| 提示音 | ✅ | ✅ | ✅ 需 ffmpeg |

语言自动检测（whisper 支持 ~100 种语言），`VD_LANG=zh` 可钉死；模型大小 `VD_MODEL=small` 可调。

## 常见问题

| 症状 | 解法 |
|---|---|
| init 报 uv 未装 | 跑上面 curl 安装命令，装完重开终端 |
| 麦克风探针失败 | macOS：系统设置→隐私与安全性→麦克风→勾选你的终端；Windows：设置→隐私→麦克风 |
| 模型下载失败/超慢 | `export HF_ENDPOINT=https://hf-mirror.com` 后重跑 |
| TTS 无声 | 检查系统输出设备是否被虚拟声卡（BlackHole 等）劫持 |
| 改了代码不生效 | MCP server 是常驻进程：`pkill -f "voice-dialog serve"` |

## 隐私

语音在本地识别（faster-whisper），文本用系统 TTS 播放，不调用任何云端 API，不上传任何音频。

## License

MIT

## 模型说明

**默认下载什么？** whisper **small**（int8 量化，约 464MB），中英文识别效果和速度的平衡点。首次 `listen`/`init` 时自动下载，之后缓存在本地（macOS/Linux：`~/.cache/huggingface/hub/`，Windows：`%USERPROFILE%\.cache\huggingface\hub\`），永不再下。

**下载源怎么选？** 代码里不写死下载逻辑——`WhisperModel("small", ...)` 构造时由 faster-whisper 库自动从 HuggingFace 下载。默认走官方源 huggingface.co；官方源连不上时代码自动切国内镜像 hf-mirror.com 重试（通过设置 `HF_ENDPOINT` 环境变量实现）。国内用户也可以提前手动钉死：

```bash
export HF_ENDPOINT=https://hf-mirror.com   # 加进 ~/.zshrc 一劳永逸
```

**换更大的模型？** 环境变量 `VD_MODEL` 控制，重跑生效：

| VD_MODEL | 大小 | 特点 |
|---|---|---|
| `tiny` | ~75MB | 最快，精度一般 |
| `base` | ~142MB | 快，日常够用 |
| `small`（默认） | ~464MB | 平衡，推荐 |
| `medium` | ~1.5GB | 更准，M 芯片秒级转写变十秒级 |
| `large-v3` | ~3GB | 最准最慢，短对话不建议 |

```bash
VD_MODEL=base uv run voice-dialog listen   # 单次用 base
```
