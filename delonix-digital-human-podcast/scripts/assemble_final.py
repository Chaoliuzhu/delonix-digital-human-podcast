#!/usr/bin/env python3
"""Final assembly: title card + segment concat + audio rebuild + glass overlays + loudnorm.

Usage:
  python3 assemble_final.py --work work --segs work/segs.json \
      --overlay-dir ov --title-big "瑞湾实践" --title-sub "AI Native 一分钟验证" \
      --cards-timeline "2,12;12,22;22,34;34,46;46,69" \
      --out final.mp4

segs.json comes from tts_sentences.py; segment mp4s must exist at work/segK.mp4
(downloaded by s2v_pipeline.py). Title duration is fixed at 2s.
"""
import argparse, json, os, subprocess
from PIL import Image, ImageDraw, ImageFont

TITLE_DUR = 2.0

def dur(f):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",f], capture_output=True, text=True)
    return float(r.stdout.strip())

def ff_width(f):
    r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=width,height","-of","csv=p=0",f], capture_output=True, text=True)
    w,h = r.stdout.strip().split(",")
    return int(w), int(h)

def font(sz):
    for p in ["/System/Library/Fonts/STHeiti Medium.ttc","/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
        try: return ImageFont.truetype(p, sz)
        except Exception: pass
    raise SystemExit("no CJK font found")

def title_card(W, H, big, sub, out):
    img = Image.new("RGB",(W,H),(26,26,46))
    d = ImageDraw.Draw(img)
    gold = (232,200,120)
    f1, f2, f3 = font(64), font(44), font(26)
    for text, f, y, c in [(big,f1,H//2-110,gold), (sub,f2,H//2-20,gold),
                          ("西安分享 · 数字人播客",f3,H//2+70,(187,187,187))]:
        w = d.textlength(text, font=f); d.text(((W-w)/2, y), text, font=f, fill=c)
    img.save("/tmp/dh_title.png")
    subprocess.run(["ffmpeg","-y","-loop","1","-i","/tmp/dh_title.png","-t",str(TITLE_DUR),
        "-r","30","-pix_fmt","yuv420p","-c:v","libx264",out], check=True, capture_output=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    ap.add_argument("--segs", required=True, help="segs.json from tts_sentences.py")
    ap.add_argument("--overlay-dir", default="ov")
    ap.add_argument("--title-big", default="瑞湾实践")
    ap.add_argument("--title-sub", default="AI Native 一分钟验证")
    ap.add_argument("--cards-timeline", default="", help="start,end per card, ; separated")
    ap.add_argument("--out", default="final.mp4")
    args = ap.parse_args()
    ABS = os.path.abspath(args.work)
    segs = json.load(open(args.segs))
    names = sorted(segs.keys(), key=lambda k: int(k.replace("seg","")))

    W, H = ff_width(f"{args.work}/{names[0]}.mp4")
    title_card(W, H, args.title_big, args.title_sub, f"{ABS}/title_card.mp4")

    # 1. video concat (silent)
    lst = f"{ABS}/concat.txt"
    with open(lst,"w") as f:
        f.write(f"file '{ABS}/title_card.mp4'\n")
        for n in names: f.write(f"file '{ABS}/{n}.mp4'\n")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-c","copy",
        f"{ABS}/joined.mp4"], check=True, capture_output=True)

    # 2. audio rebuild (concat demuxer drops audio when mixing silent title + voiced segs)
    total = TITLE_DUR + sum(dur(f"{args.work}/{n}.mp4") for n in names)
    fc = "aevalsrc=0:d=2:s=44100[sil];"
    for i, n in enumerate(names):
        fc += f"[{i+1}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];"
    fc += "[sil]" + "".join(f"[a{i}]" for i in range(len(names))) + \
          f"concat=n={len(names)+1}:v=0:a=1[out]"
    cmd = ["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo:d=2"]
    for n in names: cmd += ["-i", f"{args.work}/{n}.mp4"]
    cmd += ["-filter_complex", fc, "-map","[out]","-t",f"{total:.3f}",f"{ABS}/audio.wav"]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"total: {total:.2f}s")

    # 3. subtitle timeline (per-sentence audio durations scaled by mp4/audio ratio)
    subs = {}
    t = TITLE_DUR
    for n in names:
        info = segs[n]
        ratio = dur(f"{args.work}/{n}.mp4") / info["audio"]
        off = 0.0
        for k, si in enumerate(info["sentences"]):
            pad = 0.35 if k>0 else 0.0
            start = t + (off+pad)*ratio
            end = start + 1.0  # actual per-sentence duration needs sNN durations; approximate
            subs[si] = (start, end)
            off += pad + 1.0
        t += dur(f"{args.work}/{n}.mp4")
    # NOTE: pass real per-sentence durations via --sentence-durs for frame-accurate timing;
    # without them subtitles may drift. sNN durations are recomputed here:
    subs = {}
    t = TITLE_DUR
    for n in names:
        info = segs[n]
        mp4d = dur(f"{args.work}/{n}.mp4")
        ratio = mp4d / info["audio"]
        off = 0.0
        sents = info["sentences"]
        # per-sentence wav durations
        sdurs = [dur(f"{args.work}/s{si:02d}.mp3") for si in sents]
        for k, si in enumerate(sents):
            pad = 0.35 if k>0 else 0.0
            start = t + (off+pad)*ratio
            end = start + sdurs[k]*ratio
            subs[si] = (start, end)
            off += pad + sdurs[k]
        t += mp4d

    # 4. overlay chain
    inputs = ["-i", f"{ABS}/joined.mp4", "-i", f"{ABS}/audio.wav"]
    n_sub = 0
    while os.path.exists(f"{args.overlay_dir}/gsub{n_sub:02d}.png"): n_sub += 1
    n_card = 0
    while os.path.exists(f"{args.overlay_dir}/gcard{n_card}.png"): n_card += 1
    for i in range(n_sub): inputs += ["-i", f"{args.overlay_dir}/gsub{i:02d}.png"]
    for i in range(n_card): inputs += ["-i", f"{args.overlay_dir}/gcard{i}.png"]
    parts, cur = [], "[0:v]"
    for si in range(n_sub):
        s, e = subs.get(si, (0,0))
        parts.append(f"{cur}[{2+si}:v]overlay=(main_w-overlay_w)/2:main_h-overlay_h:"
                     f"enable='between(t,{s:.2f},{e:.2f})'[v{si}]")
        cur = f"[v{si}]"
    if args.cards_timeline:
        for ci, pair in enumerate(args.cards_timeline.split(";")):
            s, e = map(float, pair.split(","))
            parts.append(f"{cur}[{2+n_sub+ci}:v]overlay=(main_w-overlay_w)/2:40:"
                         f"enable='between(t,{s},{e:.2f})'[c{ci}]")
            cur = f"[c{ci}]"
    fc = ";".join(parts) + f";{cur}format=yuv420p[vout]"
    cmd = ["ffmpeg","-y"] + inputs + ["-filter_complex", fc, "-map","[vout]","-map","1:a",
        "-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset","medium","-crf","20",
        "-c:a","aac","-b:a","160k","-ar","44100","-movflags","+faststart","-t",f"{total:.3f}",
        args.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG ERROR:", r.stderr[-800:]); raise SystemExit(1)
    print(f"OK -> {args.out} ({dur(args.out):.2f}s, {os.path.getsize(args.out)/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()
