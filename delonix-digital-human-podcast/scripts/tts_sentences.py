#!/usr/bin/env python3
"""Per-sentence TTS + segment packing for digital-human podcast.

Usage:
  python3 tts_sentences.py --profile wanxiang \
      --sentences-file sentences.txt --outdir work/

sentences.txt: one sentence per line (blank lines ignored).
Produces: work/sNN.mp3 (per sentence), work/segK.mp3 (packed <=19s),
          work/segs.json (segment -> sentence indices + audio duration).
Requires: bl CLI, ffmpeg/ffprobe.
"""
import argparse, json, os, subprocess

def dur(f):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",f], capture_output=True, text=True)
    return float(r.stdout.strip())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="bl config profile name")
    ap.add_argument("--voice", default="longtian_v3")
    ap.add_argument("--model", default="cosyvoice-v3-flash")
    ap.add_argument("--sentences-file", required=True)
    ap.add_argument("--outdir", default="work")
    ap.add_argument("--max-seg", type=float, default=19.0)
    ap.add_argument("--pad", type=float, default=0.35, help="sentence gap seconds")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    sentences = [l.strip() for l in open(args.sentences_file, encoding="utf-8") if l.strip()]
    durs = []
    for i, s in enumerate(sentences):
        out = f"{args.outdir}/s{i:02d}.mp3"
        r = subprocess.run(["bl","speech","synthesize","--config",args.profile,
            "--model",args.model,"--voice",args.voice,"--text",s,"--out",out],
            capture_output=True, text=True)
        if not os.path.exists(out):
            print(f"s{i:02d} TTS FAILED: {r.stdout[-200:]} {r.stderr[-200:]}")
            raise SystemExit(1)
        d = dur(out); durs.append(d)
        print(f"s{i:02d} {d:5.1f}s  {s[:18]}")

    # greedy packing
    groups, cur, curd = [], [], 0.0
    for i, d in enumerate(durs):
        add = d + (args.pad if cur else 0)
        if cur and curd + add > args.max_seg:
            groups.append(cur); cur, curd = [], 0.0
            add = d
        cur.append(i); curd += add
    if cur: groups.append(cur)

    segs = {}
    for gi, g in enumerate(groups):
        out = f"{args.outdir}/seg{gi+1}.mp3"
        inputs = []
        for si in g: inputs += ["-i", f"{args.outdir}/s{si:02d}.mp3"]
        fc = "".join(f"[{k}:a]" for k in range(len(g))) + f"concat=n={len(g)}:v=0:a=1[out]"
        subprocess.run(["ffmpeg","-y"]+inputs+["-filter_complex",fc,"-map","[out]",out],
                       check=True, capture_output=True)
        segs[f"seg{gi+1}"] = {"sentences": g, "audio": dur(out)}
        print(f"seg{gi+1}: {g} -> {segs[f'seg{gi+1}']['audio']:.1f}s")
    json.dump(segs, open(f"{args.outdir}/segs.json","w"), indent=1)

if __name__ == "__main__":
    main()
