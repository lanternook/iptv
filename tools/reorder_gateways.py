#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「移动网络」实测优先级重排 curated.txt 里 CCTV 的网关线路（幂等）。

优先级（2026-10-31 手机实测 4 轮，中位 Mbps）：
  118.122.144.115:8888   11.72  直编，1~18 全通，0 失败
  219.147.245.238:25480   8.97  顺移，缺 CCTV-16
  120.40.39.246:352       6.67  顺移，CCTV-17 在 18，波动大

编号（逐台抓帧确认）：
  直编 118.122 ：1..15 直通，16 = CCTV-5+，17 = CCTV-17
  顺移 219.147 ：6 = CCTV-5+，7..16 = CCTV-6..15，17 = CCTV-17
  顺移 120.40  ：同 219.147，但 CCTV-17 在 18
用法: python reorder_gateways.py [--dry]
"""
import os, re, sys, shutil, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "output", "curated.txt")

# 直编：频道名 -> N
DIRECT = {"CCTV-1": 1, "CCTV-2": 2, "CCTV-3": 3, "CCTV-4": 4, "CCTV-5": 5,
          "CCTV-6": 6, "CCTV-7": 7, "CCTV-8": 8, "CCTV-9": 9, "CCTV-10": 10,
          "CCTV-11": 11, "CCTV-12": 12, "CCTV-13": 13, "CCTV-14": 14,
          "CCTV-15": 15, "CCTV-5+": 16, "CCTV-17": 17}

# 顺移：频道名 -> N
SHIFT = {"CCTV-1": 1, "CCTV-2": 2, "CCTV-3": 3, "CCTV-4": 4, "CCTV-5": 5,
         "CCTV-5+": 6, "CCTV-6": 7, "CCTV-7": 8, "CCTV-8": 9, "CCTV-9": 10,
         "CCTV-10": 11, "CCTV-11": 12, "CCTV-12": 13, "CCTV-13": 14,
         "CCTV-14": 15, "CCTV-15": 16, "CCTV-17": 18}

# 219.147 的 CCTV-17 在 17（18 是 404），120.40 的在 18
SHIFT17 = dict(SHIFT, **{"CCTV-17": 17})

PRIORITY = [
    ("118.122.144.115:8888", DIRECT),
    ("219.147.245.238:25480", SHIFT17),
    ("120.40.39.246:352", SHIFT),
]

GW_PAT = re.compile(r"^https?://[\d.]+:\d+/newlive/live/hls/\d+/live\.m3u8$")


def url_for(host, table, name):
    n = table.get(name)
    if n is None:
        return None
    return "http://%s/newlive/live/hls/%d/live.m3u8" % (host, n)


def main():
    dry = "--dry" in sys.argv
    old = open(SRC, encoding="utf-8").read()
    lines = old.splitlines()

    out, section = [], None
    cur_name, cur_items = None, []

    def flush():
        nonlocal cur_name, cur_items
        if cur_name is None:
            return
        others = [u for u in cur_items if not GW_PAT.match(u)]
        head = []
        for host, table in PRIORITY:
            u = url_for(host, table, cur_name)
            if u:
                head.append(u)
        out.extend("%s,%s" % (cur_name, u) for u in head + others)
        cur_name, cur_items = None, []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.endswith(",#genre#"):
            flush()
            section = s[:-len(",#genre#")]
            out.append(s)
            continue
        if "," not in s:
            flush()
            out.append(s)
            continue
        name, url = s.split(",", 1)
        if section == "央视频道":
            if name != cur_name:
                flush()
                cur_name = name
            cur_items.append(url)
        else:
            out.append(s)
    flush()

    new = "\n".join(out) + "\n"
    if new == old:
        print("无变化")
        return
    if dry:
        for d in list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                           "old", "new", lineterm=""))[:80]:
            print(d)
        return
    shutil.copyfile(SRC, SRC + ".bak")
    open(SRC, "w", encoding="utf-8", newline="\n").write(new)
    print("已重排：%d 行 -> %d 行" % (len(old.splitlines()), len(new.splitlines())))


if __name__ == "__main__":
    main()
