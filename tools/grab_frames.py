#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽 1 帧用于识台。用法: python grab_frames.py <base> <n1,n2,...> <outdir>
例: python grab_frames.py http://120.40.39.246:352 1,6,7,8,10,11,16 tmp/frames
"""
import subprocess, sys, os, re

FF = r"E:\workbuddy\tmp\ffmpeg_pkg\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

def grab(url, out):
    cmd = [FF, "-y", "-loglevel", "error",
           "-rw_timeout", "15000000",
           "-i", url, "-ss", "4", "-frames:v", "1",
           "-vf", "scale=480:-1", out]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    return r.returncode, r.stderr.decode("utf-8", "replace")[-200:]

def main():
    base = sys.argv[1].rstrip("/")
    ns = [x for x in sys.argv[2].split(",") if x]
    outdir = sys.argv[3] if len(sys.argv) > 3 else "tmp/frames"
    os.makedirs(outdir, exist_ok=True)
    tag = base.split("//")[-1].replace(":", "_").replace(".", "_")
    for n in ns:
        url = n if "://" in n else f"{base}/newlive/live/hls/{n}/live.m3u8"
        name = n if "://" not in n else re.sub(r"[^0-9A-Za-z]+", "_", url)[-60:]
        name = name.rstrip("_")
        out = os.path.join(outdir, f"{tag}__{name}.png")
        rc, err = grab(url, out)
        ok = os.path.exists(out) and os.path.getsize(out) > 0
        print(f"{tag} hls/{n}: {'OK' if ok else 'FAIL'} {'' if ok else err}")

if __name__ == "__main__":
    main()
