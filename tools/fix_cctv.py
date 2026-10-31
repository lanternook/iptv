#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_cctv.py —— 重建央视频道的备选线路（网关首条不动）。

场景：咪咕（hlsztemgsplive.miguvideo.com）的地址带鉴权参数，过期后全部返回 605。
做法：从 output/pool.txt 取 CCTV 候选（排除咪咕/网关/黑名单）→ 测速 → 每台取最快的
      若干条，接在原有网关线路后面；卫视组完全不动。

用法:
    python tools/fix_cctv.py --dry        # 只预览
    python tools/fix_cctv.py              # 写回 output/curated.txt
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from local_speedtest import measure, log, norm_channel  # noqa: E402

GW_HOST = "120.40.39.246"


def parse(path):
    groups, cur = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            groups.append((cur, []))
            continue
        if "," in s and cur is not None:
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")) and "example.com" not in u:
                groups[-1][1].append((n.strip(), u))
    return groups


def load_banned():
    p = os.path.join(ROOT, "config", "url_blacklist.txt")
    out = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--pool", default=os.path.join(ROOT, "output", "pool.txt"))
    ap.add_argument("--backups", type=int, default=2, help="每台保留几条备选（不含网关）")
    ap.add_argument("--min-mbps", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    groups = parse(a.curated)
    banned = load_banned()

    # 现有 CCTV 台名 + 现有网关线路（要保留）
    cctv_now = {}
    for gname, items in groups:
        if "央视" not in gname:
            continue
        for n, u in items:
            cctv_now.setdefault(n, []).append(u)

    # 候选：pool 里同名的、非咪咕、非网关、非黑名单
    cand = {}
    for line in open(a.pool, encoding="utf-8", errors="replace"):
        s = line.strip()
        if "," not in s:
            continue
        n, u = s.split(",", 1)
        u = u.strip()
        key = norm_channel(n)
        if key not in cctv_now:
            continue
        if "miguvideo" in u or GW_HOST in u:
            continue
        if any(k in u for k in banned):
            continue
        if u in cand.get(key, []):
            continue
        cand.setdefault(key, []).append(u)

    flat = [(k, u) for k, us in cand.items() for u in us]
    log("候选 %d 条（%d 台），开始测速..." % (len(flat), len(cand)))

    results = {}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(measure, it, a.seconds, None): it for it in flat}
        done = 0
        for fut in futs:
            it = futs[fut]
            try:
                _n, _u, mbps, note = fut.result()
            except Exception as e:  # noqa: BLE001
                mbps, note = 0.0, type(e).__name__
            results[it[1]] = mbps
            done += 1
            if done % 40 == 0:
                log("  进度 %d/%d" % (done, len(flat)))

    # 组装：网关/其他原有非咪咕线路保留，咪咕替换成测出的最快线路
    out_groups, report = [], []
    for gname, items in groups:
        if "央视" not in gname:
            out_groups.append((gname, items))
            continue
        per = {}
        for n, u in items:
            per.setdefault(n, []).append(u)
        new_items = []
        for n, urls in per.items():
            keep = [u for u in urls if "miguvideo" not in u]
            dropped = len(urls) - len(keep)
            key = norm_channel(n)
            best = sorted([(results.get(u, 0.0), u) for u in cand.get(key, [])], reverse=True)
            add = [u for m, u in best if m >= a.min_mbps and u not in keep][: a.backups]
            if not keep:
                keep = [u for m, u in best if m >= a.min_mbps][:1] or ([urls[0]] if urls else [])
            new_items.extend((n, u) for u in keep + add)
            report.append("%-8s 原 %d 条(丢咪咕 %d) → %d 条  备选速率 %s"
                          % (n, len(urls), dropped, len(keep + add),
                             ",".join("%.1f" % m for m, _u in best[:len(add)]) or "-"))
        out_groups.append((gname, new_items))

    lines = []
    for gname, items in out_groups:
        if not items:
            continue
        lines.append("%s,#genre#" % gname)
        lines.extend("%s,%s" % (n, u) for n, u in items)

    for r in report:
        log("  " + r)
    log("")
    log("总条数 %d（原 %d）" % (len(lines) - sum(1 for l in lines if "#genre#" in l),
                              sum(len(it) for _g, it in groups)))

    if a.dry:
        log("--dry：未写文件")
        return 0
    open(a.curated, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    log("已写入 %s" % a.curated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
