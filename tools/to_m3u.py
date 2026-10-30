#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""to_m3u.py —— 把 txt 订阅转成 m3u（FongMi 对 m3u 的解析更稳，可作 txt 订阅的备选）。

用法: python tools/to_m3u.py [--src output/curated.txt] [--out output/curated.m3u]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 台标（可选，播放器无网也能显示台名）
LOGO = "https://live.fanmingming.cn/tv/{name}.png"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "curated.m3u"))
    a = ap.parse_args()

    lines = ["#EXTM3U"]
    cur, count = None, 0
    for raw in open(a.src, encoding="utf-8"):
        s = raw.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            continue
        if "," not in s:
            continue
        name, url = s.split(",", 1)
        url = url.strip()
        if not url.lower().startswith(("http", "rtmp", "rtsp")):
            continue
        name = name.strip()
        lines.append('#EXTINF:-1 tvg-name="%s" tvg-logo="%s" group-title="%s",%s'
                     % (name, LOGO.format(name=name), cur or "未分组", name))
        lines.append(url)
        count += 1

    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("已写入 %s，共 %d 个频道" % (a.out, count))
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
