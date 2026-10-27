#!/usr/bin/env python3
"""wan2.2-s2v pipeline: upload -> submit -> poll -> download (raw API, no bl dependency).

Usage:
  python3 s2v_pipeline.py --key sk-... \
      --maas https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com \
      --portrait portrait.png --segs seg1.mp3 seg2.mp3 seg3.mp3 --outdir work/

Env: none needed. Reads/writes work/s2v_tasks.json and work/segK.mp4.
Requires: curl, ffmpeg/ffprobe.
"""
import argparse, json, os, subprocess, time, urllib.request, uuid

STD_BASE = "https://dashscope.aliyuncs.com/api/v1"  # task polling survives quota exhaustion

def api(url, key, payload=None, headers=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if headers: h.update(headers)
    if payload is not None:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h)
    else:
        req = urllib.request.Request(url, headers=h)
    return json.loads(urllib.request.urlopen(req, timeout=120).read())

def get_upload_policy(key, model="wan2.2-s2v"):
    d = api(f"{STD_BASE}/uploads?action=getPolicy&model={model}", key)["data"]
    return d

def upload(policy, path, name):
    ext = path.rsplit(".",1)[1]
    key = f"{policy['upload_dir']}/dh_{name}_{uuid.uuid4().hex[:8]}.{ext}"
    b = uuid.uuid4().hex
    fields = [("OSSAccessKeyId",policy["oss_access_key_id"]),("policy",policy["policy"]),
        ("signature",policy["signature"]),("key",key),
        ("x-oss-object-acl",policy["x_oss_object_acl"]),
        ("x-oss-forbid-overwrite",policy["x_oss_forbid_overwrite"]),
        ("success_action_status","200")]
    body = b""
    for k,v in fields:
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    data = open(path,"rb").read()
    body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{name}.{ext}"'
             f'\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(policy["upload_host"], data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    urllib.request.urlopen(req, timeout=300)
    return f"oss://{key}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--maas", required=True, help="workspace MaaS base URL")
    ap.add_argument("--portrait", required=True)
    ap.add_argument("--segs", nargs="+", required=True)
    ap.add_argument("--outdir", default="work")
    ap.add_argument("--resolution", default="720P")
    ap.add_argument("--poll-max", type=int, default=80)
    ap.add_argument("--poll-every", type=int, default=25)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    KEY, URL = args.key, args.maas.rstrip("/")

    # 1. upload (one policy for all files; 300s validity)
    policy = get_upload_policy(KEY)
    portrait_url = upload(policy, args.portrait, "portrait")
    audio_urls = {os.path.basename(p).rsplit(".",1)[0]: upload(policy, p, os.path.basename(p))
                  for p in args.segs}
    print("uploaded portrait +", len(audio_urls), "segments")

    # 2. submit all tasks in parallel
    tasks_path = f"{args.outdir}/s2v_tasks.json"
    tasks = json.load(open(tasks_path)) if os.path.exists(tasks_path) else {}
    for name, aurl in audio_urls.items():
        payload = {"model":"wan2.2-s2v",
            "input":{"image_url":portrait_url,"audio_url":aurl},
            "parameters":{"resolution":args.resolution,"style":"speech"}}
        r = subprocess.run(["curl","-s",f"{URL}/api/v1/services/aigc/image2video/video-synthesis",
            "-H","X-DashScope-Async: enable","-H","X-DashScope-OssResourceResolve: enable",
            "-H",f"Authorization: Bearer {KEY}","-H","Content-Type: application/json",
            "-d",json.dumps(payload)], capture_output=True, text=True)
        resp = json.loads(r.stdout)
        tid = resp.get("output",{}).get("task_id")
        print(name, "->", tid or resp)
        if tid: tasks[name] = tid
    json.dump(tasks, open(tasks_path,"w"))

    # 3. poll via STANDARD endpoint (MaaS query may 403 after quota exhaustion)
    pending = {k:v for k,v in tasks.items() if k in audio_urls or True}
    results = {}
    for rnd in range(args.poll_max):
        for name, tid in list(pending.items()):
            try:
                out = api(f"{STD_BASE}/tasks/{tid}", KEY).get("output",{})
                st = out.get("task_status")
            except Exception as e:
                print(f"[{rnd}] {name}: query error {e}"); continue
            print(f"[{rnd}] {name}: {st}", flush=True)
            if st == "SUCCEEDED":
                url = (out.get("results") or {}).get("video_url") or out.get("video_url") or ""
                results[name] = url; del pending[name]
            elif st == "FAILED":
                results[name] = f"FAILED: {out.get('code')} {out.get('message')}"; del pending[name]
        if not pending: break
        time.sleep(args.poll_every)

    # 4. download
    for name, url in results.items():
        if url.startswith("http"):
            out = f"{args.outdir}/{name}.mp4"
            subprocess.run(["curl","-sL","-o",out,url], check=True)
            print(f"downloaded {out}: {os.path.getsize(out)/1024/1024:.1f} MB")
    json.dump(results, open(f"{args.outdir}/s2v_results.json","w"), indent=1)

if __name__ == "__main__":
    main()
