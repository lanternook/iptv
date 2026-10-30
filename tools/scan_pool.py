#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_pool.py —— 扫全部订阅源，统计「哪些 host 覆盖了哪些频道」，
用于判断央视等频道是否还有优质源可挖（本地测速前先看池子有多大）。

用法: python tools/scan_pool.py [--focus CCTV-1] [--top 12]
"""
import argparse
import os
import re
import sys
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROXY = os.environ.get("IPTV_PROXY", "http://127.0.0.1:7897")
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"


def op():
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def sub_urls():
    out = []
    p = os.path.join(ROOT, "config", "subscribe.txt")
    for line in open(p, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("["):
            continue
        out.append(s.split()[0])
    return out


def parse(text):
    """同时兼容 m3u 与 txt，返回 [(name, url)]。"""
    items = []
    pending = None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#EXTINF"):
            m = re.search(r'tvg-name="([^"]+)"', s)
            name = m.group(1) if m else s.rsplit(",", 1)[-1].strip()
            pending = name
            continue
        if s.startswith("#"):
            continue
        if pending:
            if s.lower().startswith(("http", "rtmp", "rtsp")):
                items.append((pending.strip(), s))
            pending = None
            continue
        if "," in s and "#genre#" not in s:
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")):
                items.append((n.strip(), u))
    return items


def host_of(url):
    m = re.match(r"^(?:https?|rtmp|rtsp)://([^/]+)", url, re.I)
    return (m.group(1) if m else url).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--focus", default="CCTV-1")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--dump", default=None, help="把去重后的全量池写入文件，供后续分析复用")
    a = ap.parse_args()

    o = op()
    allitems = []
    for u in sub_urls():
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with o.open(req, timeout=25) as r:
                txt = r.read().decode("utf-8", "replace")
            got = parse(txt)
            allitems.extend(got)
            print("%-4d 条  %s" % (len(got), u.split("/")[-3] + "/" + u.split("/")[-1]))
        except Exception as e:  # noqa: BLE001
            print("ERR      %s  (%s)" % (u.split("/")[-1], type(e).__name__))

    uniq = {(n, u) for n, u in allitems}
    print("-" * 60)
    print("合计 %d 条，去重 %d 条" % (len(allitems), len(uniq)))
    if a.dump:
        with open(a.dump, "w", encoding="utf-8") as f:
            for n, u in sorted(uniq):
                f.write("%s,%s\n" % (n, u))
        print("已写入 %s" % a.dump)

    focus = [x for x in uniq if x[0].strip().startswith(a.focus)]
    hosts = defaultdict(set)
    for n, u in focus:
        hosts[host_of(u).split(":")[0]].add(n)
    print("\n含 %s* 的线路 %d 条，分布在 %d 个 host：" % (a.focus, len(focus), len(hosts)))
    for h, names in sorted(hosts.items(), key=lambda kv: -len(kv[1]))[:a.top]:
        print("  %-34s %2d 台  %s" % (h[:34], len(names), ",".join(sorted(names)[:6])))

    print("\n各 host 覆盖的 CCTV 台数（含 CCTV 前缀即计入）：")
    cov = defaultdict(set)
    for n, u in uniq:
        if n.strip().startswith("CCTV"):
            cov[host_of(u).split(":")[0]].add(n.strip())
    for h, names in sorted(cov.items(), key=lambda kv: -len(kv[1]))[:a.top]:
        print("  %-34s %2d 台  %s" % (h[:34], len(names), ",".join(sorted(names)[:8])))


if __name__ == "__main__":
    sys.exit(main())
