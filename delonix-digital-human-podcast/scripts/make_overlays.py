#!/usr/bin/env python3
"""Generate glassmorphism subtitle strips + carousel cards (RGBA PNG, 720px wide).

Usage:
  python3 make_overlays.py --subtitles subtitles.txt --cards cards.json --outdir ov/

subtitles.txt: one sentence per line (order = speech order).
cards.json: [{"big": "...", "small": "..."}, ...] (carousel data cards).
Output: ov/gsubNN.png (720x250 bottom gradient strip), ov/gcardK.png (720x170 glass card).
"""
import argparse, json, os
from PIL import Image, ImageDraw, ImageFont

def font(sz):
    for p in ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]:
        try: return ImageFont.truetype(p, sz)
        except Exception: pass
    raise SystemExit("no CJK font found")

def wrap(text, f, maxw, d):
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur+ch, font=f) > maxw: lines.append(cur); cur = ch
        else: cur += ch
    if cur: lines.append(cur)
    return lines

GOLD = (238,205,130)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subtitles", required=True)
    ap.add_argument("--cards", required=True)
    ap.add_argument("--outdir", default="ov")
    ap.add_argument("--width", type=int, default=720)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    W = args.width
    probe = ImageDraw.Draw(Image.new("RGB",(10,10)))
    f_sub = font(34)

    # --- subtitle strips: transparent->dark vertical gradient (no black bars) ---
    H = 250
    grad = Image.new("L",(1,H))
    for y in range(H):
        t = max(0.0, (y - H*0.35)) / (H*0.65)
        grad.putpixel((0,y), int(150 * (t**1.2)))
    grad = grad.resize((W,H))
    for i, s in enumerate(l.strip() for l in open(args.subtitles, encoding="utf-8") if l.strip()):
        lines = wrap(s, f_sub, W-80, probe)
        img = Image.new("RGBA",(W,H),(0,0,0,0)); img.putalpha(grad)
        d = ImageDraw.Draw(img)
        y = H - 30 - len(lines)*48
        for ln in lines:
            w = d.textlength(ln, font=f_sub); x = (W-w)/2
            d.text((x+1,y+1), ln, font=f_sub, fill=(0,0,0,180))
            d.text((x,y), ln, font=f_sub, fill=(255,255,255,255))
            y += 48
        img.save(f"{args.outdir}/gsub{i:02d}.png")
    print("subtitles:", i+1)

    # --- carousel cards: semi-transparent glass, gold accent ---
    cards = json.load(open(args.cards))
    CH = 170
    for i, c in enumerate(cards):
        big, small = c["big"], c.get("small","")
        sz = 50
        while sz > 26 and probe.textlength(big, font=font(sz)) > W-80: sz -= 2
        f1 = font(sz)
        sz2 = 24
        while sz2 > 16 and small and probe.textlength(small, font=font(sz2)) > W-40: sz2 -= 2
        f2 = font(sz2)
        img = Image.new("RGBA",(W,CH),(10,12,24,120))
        al = Image.new("L",(1,CH))
        for y in range(CH): al.putpixel((0,y), int(150 - 60*y/CH))
        img.putalpha(al.resize((W,CH)))
        d = ImageDraw.Draw(img)
        d.rectangle([0,0,W-1,CH-1], outline=(238,205,130,180), width=2)
        d.rectangle([0,0,8,CH-1], fill=(238,205,130,220))
        w = d.textlength(big, font=f1); d.text(((W-w)/2, 38), big, font=f1, fill=(255,240,200,255))
        if small:
            w2 = d.textlength(small, font=f2); d.text(((W-w2)/2, 116), small, font=f2, fill=(230,230,240,235))
        img.save(f"{args.outdir}/gcard{i}.png")
    print("cards:", len(cards))

if __name__ == "__main__":
    main()
