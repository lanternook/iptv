#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_ip_seg.py —— 从源池快照里按 IP 段筛线路，用于找本省运营商源。

用法:
    python tools/find_ip_seg.py --seg 120.40 --seg 111.4 --seg 117.150
    python tools/find_ip_seg.py --top 20            # 只列出现次数最多的 /16 段
"""
import argparse
import re
from collections import Counter, defaultdict

PATH = "output/pool.txt"

# xx移动常见公网段（公开分配信息，非精确 BGP 表）
GW_A_MOBILE = ("111.4.", "111.47.", "117.150.", "117.151.", "120.36.", "120.37.",
                "120.38.", "120.39.", "120.40.", "120.41.", "120.42.", "120.43.",
                "211.137.", "223.104.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seg", action="append", default=[])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--path", default=PATH)
    a = ap.parse_args()

    segs = Counter()
    seg_items = defaultdict(list)
    for line in open(a.path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if "," not in s:
            continue
        name, url = s.split(",", 1)
        m = re.match(r"^(?:https?|rtmp|rtsp)://(\d+\.\d+\.\d+\.\d+)", url, re.I)
        if not m:
            continue
        ip = m.group(1)
        k = ".".join(ip.split(".")[:2]) + "."
        segs[k] += 1
        seg_items[k].append((name.strip(), url.strip(), ip))

    print("IP 型线路 %d 条，涉及 %d 个 /16 段\n" % (sum(segs.values()), len(segs)))
    print("出现最多的 /16 段：")
    for k, c in segs.most_common(a.top):
        mark = "  ← xx移动段" if k in GW_A_MOBILE else ""
        print("  %-10s %3d 条%s" % (k, c, mark))

    targets = a.seg or [k for k in segs if k in GW_A_MOBILE]
    if not targets:
        print("\n未指定 --seg，且池内无xx移动段")
        return
    print("\n目标段明细：")
    for t in targets:
        t = t if t.endswith(".") else t + "."
        hits = [(k, v) for k, v in seg_items.items() if k.startswith(t)]
        total = sum(len(v) for _, v in hits)
        print("\n[%s*] 命中 %d 条" % (t, total))
        for k, items in hits:
            for name, url, ip in items[:12]:
                print("  %-12s %-16s %s" % (name, ip, url[:88]))
            if len(items) > 12:
                print("  ... 该段还有 %d 条" % (len(items) - 12))


if __name__ == "__main__":
    main()
