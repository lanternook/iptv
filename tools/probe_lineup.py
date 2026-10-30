#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比两个 newlive/live/hls 网关的逐台签名（可用性 + TARGETDURATION），判断编排是否同源。
用法: python probe_lineup.py <base1> <base2>  例: http://a:352 http://b:8888
"""
import urllib.request, re, sys

UA = {"User-Agent": "okhttp/3.12.0"}

def probe(base, n):
    url = f"{base}/newlive/live/hls/{n}/live.m3u8"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=6)
        txt = r.read().decode("utf-8", "replace")
        td = re.search(r"#EXT-X-TARGETDURATION:(\d+)", txt)
        return ("OK", td.group(1) if td else "?")
    except Exception as e:
        return ("--", type(e).__name__[:6])

def main():
    b1, b2 = sys.argv[1], sys.argv[2]
    ns = list(range(1, 21)) + [22, 24, 28, 29, 30, 32, 34, 35, 36]
    print(f"{'N':>3} | {b1.split('//')[-1]:>16} | {b2.split('//')[-1]:>16}")
    diff = 0
    for n in ns:
        s1, t1 = probe(b1, n)
        s2, t2 = probe(b2, n)
        mark = "" if (s1, t1) == (s2, t2) else "  <-- 不同"
        if mark: diff += 1
        print(f"{n:>3} | {s1:>4} td={t1:>2}      | {s2:>4} td={t2:>2}      {mark}")
    print(f"\n签名不一致的台: {diff}/{len(ns)}")

if __name__ == "__main__":
    main()
