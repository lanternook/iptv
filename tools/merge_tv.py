#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_tv.py —— 以电视端实测结果为底，叠加xx移动网关源（同省优先）。

规则：
  1. 底表 = 电视端测速结果（顺序即该网络下的速率降序）
  2. xx网关源（config/extra_gw_a.txt）插到对应台的**第一条**，其余线路顺延为备选
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
    ap.add_argument("--gw", default=os.path.join(ROOT, "config", "extra_gw_a.txt"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--per-channel", type=int, default=6)
    ap.add_argument("--drop-group", action="append", default=[], help="整组丢弃，如 --drop-group 凤凰频道")
    ap.add_argument("--move", action="append", default=[], help="台名=目标分组，如 --move 广州综合=卫视频道")
    ap.add_argument("--rates", default=os.path.join(ROOT, "output", "rates.tsv"),
                    help="测速速率表（name\\tmbps\\turl），由 local_speedtest.py 生成")
    ap.add_argument("--min-mbps", type=float, default=2.0,
                    help="严格组的速率门槛，低于此值的线路丢弃")
    ap.add_argument("--strict-group", action="append", default=["卫视"],
                    help="启用速率过滤的分组关键字，可多次；默认 卫视")
    ap.add_argument("--no-filter", action="store_true", help="关闭速率过滤，全量输出")
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

    # 速率表：URL -> Mbps，用于严格组的低速率过滤；同时按台名聚合供回补
    rates = {}
    by_name = {}
    if not a.no_filter and os.path.exists(a.rates):
        for line in open(a.rates, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                try:
                    m = float(parts[1])
                except ValueError:
                    continue
                u = parts[2].strip()
                rates[u] = m
                by_name.setdefault(parts[0].strip(), []).append((m, u))
        for k in by_name:
            by_name[k].sort(reverse=True)
        print("速率表 %d 条（门槛 %.1f Mbps）" % (len(rates), a.min_mbps))
    elif not a.no_filter:
        print("!! 未找到速率表 %s，本次不做速率过滤" % a.rates)

    def is_strict(gname):
        return not a.no_filter and any(k in gname for k in a.strict_group)

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
    dropped_low = []
    rescued = []
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
        strict = is_strict(gname)
        low_drop = []
        for n in order:
            urls = bucket[n]
            if n in gw:
                g = gw[n]
                urls = [g] + [u for u in urls if u != g]
                gw_hit += 1
            picked = []
            for u in urls:
                # 有速率记录且低于门槛 -> 丢弃；无记录的不误杀
                if strict and u in rates and rates[u] < a.min_mbps:
                    continue
                picked.append(u)
                if len(picked) >= a.per_channel:
                    break
            if strict and not picked:
                # 底表内全不达标：从速率表里回补该台达标的线路，避免误杀
                alts = [u for m, u in by_name.get(n, [])
                        if m >= a.min_mbps and not banned(u) and u not in picked]
                picked = alts[: a.per_channel]
                if picked:
                    rescued.append(n)
            if strict and not picked:
                low_drop.append(n)
                continue
            for u in picked:
                out.append("%s,%s" % (n, u))
        if out:
            lines.append("%s,#genre#" % gname)
            lines.extend(out)
        stat.append((gname, len(order), len(out), gw_hit, len(low_drop)))
        if low_drop:
            dropped_low.extend(low_drop)

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
    for g, ch, ln, hit, drop in stat:
        tail = "  低速率丢弃 %d 台" % drop if drop else ""
        print("  %-10s %2d 台 %3d 条  网关优先 %d 台%s" % (g, ch, ln, hit, tail))
    if dropped_low:
        print("  丢弃台（无任何达标线路，<%.1f Mbps）: %s" % (a.min_mbps, ",".join(dropped_low)))
    if rescued:
        print("  回补台（底表线路不达标，改用速率表线路）%d 台: %s"
              % (len(rescued), ",".join(rescued)))
    if missing:
        print("  网关补充（电视端缺失）: %s" % ",".join(missing))
    print("总条数 %d" % (len(lines) - 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
