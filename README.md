# voice-dialog-mcp — 给任意 Agent 的本地语音对话能力

MCP server + CLI 双形态。纯本地：TTS 走系统原生，ASR 用 faster-whisper（本地推理），端点检测用 webrtcvad（纯信号处理，非模型）。

## 工具
- `speak(text)` — 播完即返回（终态播报）
- `listen(wait_start, silence, max_len)` — VAD 录音 + 本地转写
- `ask_by_voice(text, wait_start=30, silence=5)` — 原子单回合：说一句听一次，**绝不自动续听**（防死循环）
- `doctor` — 环境体检（ffmpeg/麦克风/TTS/模型/1秒实录探针）

## 交互时序（用户听到的）
高音"叮"= 开录 → 说话 → 静默 5 秒 → 下行双音 = 正常结束（急促三连音 = 60 秒硬顶截断）

## 接入
```json
{ "mcpServers": { "voice-dialog": {
  "command": "uv", "args": ["--project", "/Users/victor/Documents/work/AI/2026-08-21--voice-dialog-mcp", "run", "voice-dialog", "serve"] } } }
```
CLI：`voice-dialog speak "…" | listen | ask "…" | doctor | serve`

## 设计要点
- 语言 auto 检测（whisper ~100 语言），`VD_LANG` 可钉死；中文 TTS 文本走 UTF-8 文件规避 Win PS5.1 GBK 坑
- 模型缺失首次自动下载，HF_ENDPOINT→hf-mirror.com 回退（中国网络）
- 平台差异全部收敛在 platform.py（macOS say / Win SAPI / Linux espeak；ffmpeg 兜底录音）
- mcp 钉在 >=1.17,<2.0（2.0 删了装饰器 API）
- webrtcvad 需要 setuptools<82（pkg_resources）
- 本机注意：默认输入是 BlackHole 2ch（回环设备）时必须显式选物理麦克风，设备 1 = MacBook Air麦克风

## 验证记录（2026-08-21）
- doctor：全部 ok（ffmpeg/麦克风×2/say/模型缓存/实录探针）
- speak：say 中文发声正常
- listen：录音→VAD→whisper 全链路通（无人说话返回 no_speech/空文本）
- MCP：stdio 握手 + tools/list + tools/call(doctor) 实测通过
- Claude Code：user 级已注册（voice-dialog），Skill 装在 ~/.claude/skills/hcn-voice-dialog/

## 验收记录（2026-08-21，主人真机参与）
- 真人语音识别：全对（"晚饭想吃米饭"“明天是周五"，含长句复杂反馈均准确转写）
- 完整 ask 闭环：提问→叮→回答→5秒静默→咚咚→转写返回 ✓
- 提示音可听性确认：主人听到两组提示音 ✓

## 调试中修掉的 3 个真坑（开源后别人也会踩）
1. **ffplay 不跟随系统默认输出设备**：ffmpeg 的 ffplay 在 macOS 上自己挑 core-audio 设备（选中 BlackHole 回环），rc=0 但用户听不到。修法：ffmpeg 渲染 wav → afplay/powershell SoundPlayer 播放（跟随系统输出）
2. **macOS 中文声音选择**：`say -v ?` 里 zh_CN 按字母序 Eddy/Flo/Grandma 排前面，都是劣质音色且部分静默失败；必须优先 Tingting/Meijia/Sinji
3. **faster-whisper confidence 恒 0**：原实现误把"段时长均值/总时长"当置信度；改为 speech coverage（语音覆盖率），>0.25 才算正常
