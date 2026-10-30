#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把多张帧拼成带序号的联系表（5列网格，顺序=传入顺序）。
用法: python make_sheet.py <outdir> <out.png> <f1> <f2> ...
"""
import subprocess, sys, os, shutil

FF = r"E:\workbuddy\tmp\ffmpeg_pkg\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

def main():
    outdir, outpng = sys.argv[1], sys.argv[2]
    frames = sys.argv[3:]
    seqdir = os.path.join(outdir, "_seq")
    shutil.rmtree(seqdir, ignore_errors=True)
    os.makedirs(seqdir, exist_ok=True)
    for i, f in enumerate(frames, 1):
        src = os.path.join(outdir, f) if not os.path.isabs(f) else f
        shutil.copy(src, os.path.join(seqdir, f"{i:02d}.png"))
    cols = 5
    rows = (len(frames) + cols - 1) // cols
    vf = ("scale=480:270:force_original_aspect_ratio=decrease,"
          "pad=480:270:(ow-iw)/2:(oh-ih)/2:color=black,"
          f"tile={cols}x{rows}")
    cmd = [FF, "-y", "-loglevel", "error", "-framerate", "1",
           "-i", os.path.join(seqdir, "%02d.png"),
           "-vf", vf, "-frames:v", "1", "-update", "1", outpng]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    print("sheet:", outpng, "OK" if os.path.exists(outpng) else "FAIL",
          "" if r.returncode == 0 else r.stderr.decode("utf-8", "replace")[-300:])

if __name__ == "__main__":
    main()
