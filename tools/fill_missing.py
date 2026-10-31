#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_missing.py —— 用测速结果补回订阅里"整台消失"的频道。

场景：某批源失效被删后，若干台一条不剩。从测速结果（local_speedtest 的 --out 产物，
已是按速率降序）里把缺失的台补回来，插到原位置。

用法:
    python tools/fill_missing.py --src tmp/ws_new.txt --group 卫视频道 --dry
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def parse(path):
    groups, cur = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            groups.append([cur, []])
            continue
        if "," in s and cur is not None:
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")) and "example.com" not in u:
                groups[-1][1].append((n.strip(), u))
    return groups


def load_template(path):
    """模板里是纯台名（无 URL），单独解析。"""
    out, cur = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            out[cur] = []
            continue
        if cur is not None and "," not in s:
            out[cur].append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--src", required=True, help="测速结果文件")
    ap.add_argument("--group", default="卫视频道")
    ap.add_argument("--tpl", default=os.path.join(ROOT, "config", "user_demo.txt"),
                    help="模板，用来确定该组应有的台与顺序")
    ap.add_argument("--per-channel", type=int, default=2)
    ap.add_argument("--ban", action="append", default=["miguvideo.com"],
                    help="候选 URL 含这些关键字就跳过，可多次")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    cur_groups = parse(a.curated)
    src = {g: items for g, items in parse(a.src)}
    tpl = load_template(a.tpl)

    have = {n for g, items in cur_groups if g == a.group for n, _u in items}
    want = tpl.get(a.group, [])
    cand = {}
    for n, u in src.get(a.group, []):
        if any(k in u for k in a.ban):
            continue
        cand.setdefault(n, []).append(u)

    added = []
    for g, items in cur_groups:
        if g != a.group:
            continue
        for n in want:
            if n in have or n not in cand:
                continue
            for u in cand[n][: a.per_channel]:
                items.append((n, u))
                added.append("%s ← %s" % (n, u[:56]))
    print("缺失台 %d，可从测速结果补回 %d 台"
          % (len([n for n in want if n not in have]), len(added) and len({x.split(' ←')[0] for x in added})))
    for x in added:
        print("  " + x)

    if a.dry:
        print("--dry：未写文件")
        return 0
    lines = []
    for g, items in cur_groups:
        if not items:
            continue
        lines.append("%s,#genre#" % g)
        lines.extend("%s,%s" % (n, u) for n, u in items)
    open(a.curated, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("已写入 %s（%d 条）" % (a.curated, len([l for l in lines if "#genre#" not in l])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
