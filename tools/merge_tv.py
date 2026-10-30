#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_tv.py —— 以电视端实测结果为底，叠加湖北移动网关源（同省优先）。

规则：
  1. 底表 = 电视端测速结果（顺序即该网络下的速率降序）
  2. 湖北网关源（config/extra_hubei.txt）插到对应台的**第一条**，其余线路顺延为备选
  3. 同台内 URL 去重，每台最多保留 --per-channel 条
  4. 只输出 txt（不出 m3u）

用法: python tools/merge_tv.py [--tv output/tv_result.txt] [--out output/curated.txt]
"""
import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CCTV_RE = re.compile(r"^CCTV-(\d+)(\+?)")


def cctv_key(name, rank):
    """央视按台号自然序排前面；非央视保持底表相对顺序。"""
    m = CCTV_RE.match(name)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, 0)
    return (1, 0, 0, rank.get(name, 0))


def parse_groups(path):
    """返回 [(组名, [(台名, url)])]，保持原顺序。"""
    groups, cur = [], None
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            groups.append([cur, []])
            continue
        if "," in s:
            if cur is None:  # 无 #genre# 头的纯 name,url 文件
                cur = "__PLAIN__"
                groups.append([cur, []])
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")):
                groups[-1][1].append((n.strip(), u))
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tv", default=os.path.join(ROOT, "output", "tv_result.txt"))
    ap.add_argument("--gw", default=os.path.join(ROOT, "config", "extra_hubei.txt"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--per-channel", type=int, default=6)
    ap.add_argument("--drop-group", action="append", default=[], help="整组丢弃，如 --drop-group 凤凰频道")
    ap.add_argument("--move", action="append", default=[], help="台名=目标分组，如 --move 广州综合=卫视频道")
    a = ap.parse_args()

    moves = {}
    for m in a.move:
        if "=" in m:
            k, v = m.split("=", 1)
            moves[k.strip()] = v.strip()

    # URL 黑名单：命中关键字的线路直接丢弃
    bad = []
    bl = os.path.join(ROOT, "config", "url_blacklist.txt")
    if os.path.exists(bl):
        for line in open(bl, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                bad.append(s)
    def banned(u):
        return any(k in u for k in bad)
    if bad:
        print("URL 黑名单 %d 条" % len(bad))

    tv = parse_groups(a.tv)
    gw = {}
    for _gname, _items in parse_groups(a.gw):
        for n, u in _items:
            if not banned(u):
                gw[n] = u
    print("网关映射 %d 台" % len(gw))

    lines = ["🕘️更新时间,#genre#",
             "%s,https://example.com/ping" % time.strftime("%Y-%m-%d %H:%M:%S")]
    stat = []
    # 先把要迁移的台从原组摘出来
    moved = {}
    for gname, items in tv:
        if "更新时间" in gname:
            continue
        keep = []
        for n, u in items:
            if banned(u):
                continue
            if n in moves:
                moved.setdefault(moves[n], []).append((n, u))
            else:
                keep.append((n, u))
        items[:] = keep

    for gname, items in tv:
        if "更新时间" in gname or gname in a.drop_group:
            if gname in a.drop_group:
                print("丢弃分组: %s（%d 条）" % (gname, len(items)))
            continue
        items = items + moved.pop(gname, [])
        # 按台聚合，保持出现顺序
        order, bucket = [], {}
        for n, u in items:
            if n not in bucket:
                bucket[n] = []
                order.append(n)
            if u not in bucket[n]:
                bucket[n].append(u)

        # 央视按台号自然序（1,2,...,5,5+,6...），其余保持原相对顺序
        rank = {n: i for i, n in enumerate(order)}
        order.sort(key=lambda n: cctv_key(n, rank))

        out = []
        gw_hit = 0
        for n in order:
            urls = bucket[n]
            if n in gw:
                g = gw[n]
                urls = [g] + [u for u in urls if u != g]
                gw_hit += 1
            for u in urls[: a.per_channel]:
                out.append("%s,%s" % (n, u))
        if out:
            lines.append("%s,#genre#" % gname)
            lines.extend(out)
        stat.append((gname, len(order), len(out), gw_hit))

    # 目标分组不存在的迁移项，单独补一组
    for tgt, items in moved.items():
        if items:
            lines.append("%s,#genre#" % tgt)
            for n, u in items:
                lines.append("%s,%s" % (n, u))
            print("补建分组 %s（%d 条）" % (tgt, len(items)))

    # 网关有、但电视结果里没有的台（如某台电视端全灭），用网关补上
    missing = [n for n in gw if not any(n in [x[0] for x in items] for _, items in tv)]
    if missing:
        lines.append("央视频道补,#genre#")
        for n in missing:
            lines.append("%s,%s" % (n, gw[n]))

    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("写入 %s" % a.out)
    for g, ch, ln, hit in stat:
        print("  %-10s %2d 台 %3d 条  网关优先 %d 台" % (g, ch, ln, hit))
    if missing:
        print("  网关补充（电视端缺失）: %s" % ",".join(missing))
    print("总条数 %d" % (len(lines) - 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
