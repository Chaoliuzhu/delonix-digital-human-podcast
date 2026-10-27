# Aliyun Bailian Digital-Human API Notes (battle-tested 2026-10-27)

All traps below were hit and resolved in a real end-to-end run. Config used:
`bl auth login --config <profile> --api-key <key> --base-url https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com`

## wan2.2-s2v (digital human, audio-driven)

- **Correct endpoint**: `POST {maas}/api/v1/services/aigc/image2video/video-synthesis`
  - The `video-generation/video-synthesis` path (used by wan3.0 t2v) returns a misleading
    `"url error, please check url"` for s2v — it is a WRONG-PATH error, not a URL problem.
- **Headers**: `X-DashScope-Async: enable`, `X-DashScope-OssResourceResolve: enable` (required
  for oss:// temp-storage URLs), `Authorization: Bearer <key>`.
- **Body**:
  ```json
  {
    "model": "wan2.2-s2v",
    "input": { "image_url": "oss://...", "audio_url": "oss://..." },
    "parameters": { "resolution": "720P", "style": "speech" }
  }
  ```
- **Audio limit: 20 seconds.** Longer audio fails asynchronously with
  `"The input audio is longer than 20s."` (task-level FAILED, minutes after submit). Pack audio
  into ≤19s segments BEFORE submitting.
- **Audio format**: 24kHz mono mp3/wav works. 720P output is 720x1048 for a 3:4 portrait
  (output follows input image aspect), 30fps H.264 + AAC.
- **Task query**: `GET {maas}/api/v1/tasks/{task_id}`.
  - `video_url` is at `output.results.video_url` (s2v) or `output.video_url` (wan3.0 t2v) —
    check both.
  - **Quota trap**: once the workspace's s2v quota is exhausted, the MaaS tasks-query endpoint
    itself returns `403 AccessDenied.Unpurchased` EVEN for already-submitted tasks. Poll via the
    standard endpoint instead: `GET https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}` —
    it works with the same workspace key and survives quota exhaustion.
- **Cost**: 480P ¥0.5/s, 720P ¥0.9/s of output video. 65s script @720P ≈ ¥59.
- `video_url` expires in 24h — download immediately.

## DashScope temp-storage upload (for local files)

1. `GET https://dashscope.aliyuncs.com/api/v1/uploads?action=getPolicy&model=wan2.2-s2v`
   (the `model` param is REQUIRED — omitting it returns a generic InvalidParameter).
   Response `data` contains: `policy`, `signature`, `upload_dir`, `upload_host`,
   `oss_access_key_id`, `x_oss_object_acl`, `x_oss_forbid_overwrite`. Policy expires in 300s.
2. OSS form-POST to `upload_host` with fields: OSSAccessKeyId, policy, signature, key
   (`{upload_dir}/name.ext`), x-oss-object-acl, x-oss-forbid-overwrite, success_action_status=200,
   file (multipart, file field last).
3. Resulting URL: `oss://{key}` — pass to APIs WITH the OssResourceResolve header.
4. `bl` CLI uploads automatically when given a local path, but its dry-run also prints
   (unuploaded) plausible oss:// paths — do not trust dry-run URLs.

## TTS

### cosyvoice-v3-flash (preferred)

`bl speech synthesize --config <profile> --model cosyvoice-v3-flash --voice longtian_v3 --text "..." --out x.mp3`
- `--list-voices` to browse (26 voices: longtian_v3 磁性理智男, longcheng_v3 智慧青年男,
  longanyang 阳光大男孩, etc.).
- Quota is separate from s2v; free tier ran out after ~15 calls in testing. Returns
  `403 AccessDenied.Unpurchased` when exhausted.

### qwen-audio-3.1-tts-next (voice cloning)

- **`bl speech synthesize` is BROKEN for this model** (sends `input.text` + `voice`, the model
  expects `input.text_prompt` → `"text_prompt must not be empty"`). Use raw HTTP.
- Endpoint: `POST {maas}/api/v1/services/audio/tts/SpeechSynthesizer`
  ```json
  {
    "model": "qwen-audio-3.1-tts-next",
    "input": {
      "text_prompt": "@voice1 用参考音频中同样的男声说：「……」",
      "references": [ { "audio_data": "data:audio/mpeg;base64,<b64>" } ],
      "format": "mp3", "sample_rate": 24000, "channels": 1, "rate": 1.0
    }
  }
  ```
- `references` entries are OBJECTS (`{"audio_data": ...}` or `{"audio_url": ...}`) — bare strings
  are silently ignored → error `"@voice1 in text_prompt does not match any reference (total 0)"`.
- No traditional voice IDs; the persona is described inside text_prompt.
- References: ≤3 clips, each ≤30s / ≤10MB, WAV/MP3/OGG.
- Response: `output.audio.url` (24h validity) + `output.audio.duration`.
- **Clone-quality trap**: cloning may hallucinate trailing repeats (e.g. last 3 words repeated
  with silence gaps). Verify with an omni model transcription pass and trim: detect speech
  segments via `silencedetect=noise=-30dB:d=0.3`, cut the valid span, fade out 1s.
- Single generation cap: 120s (240s for podcast-style scenes).

### Piper (offline fallback)

Open-source neural TTS, `zh_CN-huayan-medium.onnx` (~63MB). Robotic cadence — use `--length-scale
1.05 --sentence-silence 0.3` and accept lower naturalness. Last-resort only.

## wan2.7-image (portrait gen / edit)

- `bl image generate --model wan2.7-image --size 3:4 --watermark false --prompt "..."` (sync mode,
  ~10s). Use `--size`, NOT `--ratio`.
- Two-image composite (real person into real background):
  `bl image edit --model wan2.7-image --image <selfie> --image <venue-photo> --prompt "保持第一张图人物面部五官、发型、眼镜、服装完全不变，将其自然融入第二张图的场景中，半身正面构图，直视镜头，背景轻微虚化，真实商业人像摄影质感"`
  — repeat `--image` for multi-image; explicit "keep unchanged" phrasing preserves identity.

## Image-gen output URL

Sync image-gen returns a signed OSS URL (24h validity) — download immediately; do not hotlink
into long-lived pages.

## Transcription (verification)

`bl omni --config <profile> --model qwen3.8-omni-flash --message "逐字转写语音内容" --audio x.mp3
--text-only --base-url https://dashscope.aliyuncs.com` — omni works as ASR when fun-asr quota is
gone. Append `--base-url https://dashscope.aliyuncs.com` if the MaaS endpoint proxy fails (502).

## Web embed trap

Share-site platforms (e.g. workbuddy sites) commonly gate non-HTML assets behind the share-code
query param: `video.mp4` → 403, `video.mp4?sharecode=XXX` → 200. Browsers do NOT propagate the
page's query string to relative-path resource requests, so hardcode the sharecode in `src` or
inline the file as a base64 data URI.
