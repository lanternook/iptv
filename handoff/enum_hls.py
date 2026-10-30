#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enum_hls.py —— 枚举 IPTV 转 HLS 网关的频道号，找同省运营商源。

很多省运营商 IPTV 会有一个"公网可访问的转发网关"，形如：
    http://IP:PORT/newlive/live/hls/{N}/live.m3u8
    http://IP:PORT/tsfile/live/{N}_1.m3u8
频道号 N 连续或半连续，枚举即可捞出整批可用台（同省移动/电信下速度接近内网）。

用法:
    python tools/enum_hls.py --tpl "http://120.40.39.246:352/newlive/live/hls/{n}/live.m3u8" --from 1 --to 60
    python tools/enum_hls.py --tpl "http://1.2.3.4:9901/tsfile/live/{n}_1.m3u8" --from 1 --to 200 --workers 8
"""
import argparse
import concurrent.futures as cf
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 直连


def get(url, timeout=5, max_bytes=65536):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    with OP.open(req, timeout=timeout) as r:
        data = r.read(max_bytes)
    return data, time.time() - t0


def first_segment(text, base):
    variants = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    variants.append(urllib.parse.urljoin(base, nxt))
                    break
    if variants:
        return variants[0]
    for line in lines:
        if not line.startswith("#"):
            return urllib.parse.urljoin(base, line)
    return None


def probe(n, tpl, seconds):
    url = tpl.format(n=n)
    try:
        data, el = get(url, 6)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, OSError):
        return n, url, 0.0, "连接失败"
    text = data.decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        return n, url, 0.0, "非 m3u8"
    seg = first_segment(text, url)
    if not seg:
        return n, url, 0.0, "无分片"
    try:
        req = urllib.request.Request(seg, headers={"User-Agent": UA})
        t0 = time.time()
        total = 0
        with OP.open(req, timeout=6) as r:
            while time.time() - t0 < seconds:
                chunk = r.read(16384)
                if not chunk:
                    break
                total += len(chunk)
        el = max(time.time() - t0, 0.01)
        return n, url, round(total * 8 / el / 1_000_000, 2), "%dKB" % (total // 1024)
    except Exception:  # noqa: BLE001
        return n, url, 0.0, "分片失败"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tpl", required=True, help='URL 模板，用 {n} 占位频道号')
    ap.add_argument("--from", dest="lo", type=int, default=1)
    ap.add_argument("--to", dest="hi", type=int, default=60)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--min-mbps", type=float, default=0.5)
    a = ap.parse_args()

    ids = list(range(a.lo, a.hi + 1))
    print("枚举 %d 个频道号，模板 %s" % (len(ids), a.tpl))
    ok = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for n, url, mbps, note in ex.map(lambda i: probe(i, a.tpl, a.seconds), ids):
            if mbps >= a.min_mbps:
                ok.append((mbps, n, url))
                print("  ✓ %-4d %6.2f Mbps  %s" % (n, mbps, note))
    print("-" * 56)
    ok.sort(key=lambda x: -x[0])
    print("可用 %d/%d 个" % (len(ok), len(ids)))
    for mbps, n, url in ok:
        print("%-4d %6.2f  %s" % (n, mbps, url))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
