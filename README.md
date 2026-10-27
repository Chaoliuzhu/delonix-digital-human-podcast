# delonix-digital-human-podcast

数字人播客视频全链路生成 SKILL —— 一次实战全流程沉淀（脚本→TTS→肖像合成→s2v 分段→玻璃字幕拼装→网页嵌入）。

## 这是什么

给定一段约 1 分钟的口播主题，本 SKILL 让 AI Agent 完整产出一条「真人出镜」数字人播客视频：

- 🎙️ 逐句 TTS（cosyvoice-v3 磁性男声 / qwen-audio 声音克隆 / Piper 兜底）
- 🧑‍💼 真实人物照片 + 真实场景照片 → wan2.7-image 保真合成底图（五官/眼镜不变）
- 🎬 wan2.2-s2v 数字人驱动（20 秒音频上限的自动分段并行策略）
- 💬 玻璃拟态字幕（渐变融入背景，无黑底条）+ 轮播数据卡 + 标题卡
- 🔊 音轨重建（防 concat 丢音）、loudnorm 归一
- 🌐 一键嵌入分享页（含 sharecode 资源保护机制处理）

## 实测样例

2026-10-27 西安「AI 神灯」分享 · 69 秒数字人播客：
本人形象 + 酒店大堂实景 + 磁性男声 + 玻璃字幕轮播卡，全流程 API 自动化。

## 安装（WorkBuddy）

```bash
# 方式一：解压 zip 到技能目录
unzip delonix-digital-human-podcast.zip -d ~/.workbuddy/skills/

# 方式二：直接克隆
git clone https://github.com/Chaoliuzhu/delonix-digital-human-podcast.git \
  ~/.workbuddy/skills/delonix-digital-human-podcast
```

## 结构

```
delonix-digital-human-podcast/
├── SKILL.md                    # 7 步主流程
├── references/api-notes.md     # 百炼 API 全部实战坑（端点/额度/参数）
└── scripts/
    ├── tts_sentences.py        # 逐句 TTS + 19s 分段打包
    ├── s2v_pipeline.py         # 上传→提交→轮询→下载（原生 API）
    ├── make_overlays.py        # 玻璃字幕 + 轮播卡（PIL RGBA）
    └── assemble_final.py       # 标题卡+拼接+音轨重建+overlay+loudnorm
```

## 依赖

- 阿里云百炼工作区 Key（wan2.2-s2v / wan2.7-image / cosyvoice-v3-flash / qwen-audio-3.1-tts-next）
- ffmpeg（无需 drawtext/subtitles 滤镜）、Python3 + Pillow

## License

MIT
