#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grab_frames2.py —— 批量抓帧识台标，专治「带 query 的 URL」。

为什么不直接用 grab_frames.py：它拿 URL 末段当输出文件名，
遇到 `.../1023_1.m3u8?key=txiptv&playlive=1&down=1` 会生成含 `?` `&` `=` 的非法文件名
（Windows 下直接失败，或报 Error muxing a packet）。本脚本**只用清单里的标签当文件名**。

用法:
    python tools/grab_frames2.py 清单.txt 输出目录
    python tools/grab_frames2.py 清单.txt 输出目录 --seek 5 --width 480

清单格式（每行一条）:
    标签|URL

输出：<输出目录>/<标签>.png，已存在的跳过（可断点续抓）。
抓完用看图工具逐张认台标 —— 编号映射**必须这样验**，按规律硬套必错。
"""
import argparse
import os
import subprocess
import sys

# ffmpeg 位置（项目内复用 imageio-ffmpeg 的二进制；不存在时退回 PATH 里的 ffmpeg）
CANDIDATES = [
    r"tools/ffmpeg_pkg/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe",
    r"ffmpeg.exe",
]


def find_ffmpeg():
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    return "ffmpeg"


def safe_name(tag):
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in tag).strip()
    return out or "frame"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="清单文件（标签|URL）")
    ap.add_argument("outdir", help="输出目录")
    ap.add_argument("--seek", type=float, default=3.0, help="第几秒抓帧，默认 3")
    ap.add_argument("--width", type=int, default=420, help="缩放宽度，默认 420")
    ap.add_argument("--timeout", type=int, default=45, help="单条超时秒数，默认 45")
    args = ap.parse_args()

    ff = find_ffmpeg()
    os.makedirs(args.outdir, exist_ok=True)

    lines = []
    for raw in open(args.src, encoding="utf-8"):
        s = raw.strip()
        if s and not s.startswith("#") and "|" in s:
            tag, url = s.split("|", 1)
            lines.append((tag.strip(), url.strip()))

    if not lines:
        print("清单为空或格式不对（需要 `标签|URL`）")
        return 1

    ok = fail = skip = 0
    for tag, url in lines:
        out = os.path.join(args.outdir, safe_name(tag) + ".png")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            print("%-10s SKIP" % tag, flush=True)
            skip += 1
            continue
        cmd = [ff, "-y", "-loglevel", "error", "-rw_timeout", "15000000",
               "-i", url, "-ss", str(args.seek), "-frames:v", "1",
               "-vf", "scale=%d:-1" % args.width, out]
        try:
            subprocess.run(cmd, capture_output=True, timeout=args.timeout)
            good = os.path.exists(out) and os.path.getsize(out) > 0
        except subprocess.TimeoutExpired:
            good = False
        print("%-10s %s" % (tag, "OK" if good else "FAIL"), flush=True)
        ok += 1 if good else 0
        fail += 0 if good else 1

    print("\nOK %d / FAIL %d / SKIP %d → %s" % (ok, fail, skip, args.outdir))
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
