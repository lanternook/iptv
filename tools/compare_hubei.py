#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载各 hls/N 的首个分片，做 md5 指纹，找出同一路流（重复台）并观察错位。"""
import urllib.request, hashlib, re, sys

GW = "http://120.40.39.246:352"
BASE = GW + "/newlive/live/hls/{n}/"
NS = [1,3,5,6,7,8,9,10,11,12,13,14,15,16,18,19,20,22,24]

def get(url, timeout=10, maxbytes=None):
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/3.12.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(maxbytes) if maxbytes else r.read()
        return r.status, data

def main():
    rows = []
    for n in NS:
        base = BASE.format(n=n)
        try:
            st, pl = get(base + "live.m3u8")
            txt = pl.decode("utf-8", "replace")
            seq = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", txt)
            td = re.search(r"#EXT-X-TARGETDURATION:(\d+)", txt)
            segs = re.findall(r"^(program-\d+\.ts)$", txt, re.M)
            seg = segs[0] if segs else None
            md5 = "-"
            size = 0
            if seg:
                st2, data = get(base + seg, maxbytes=400000)
                md5 = hashlib.md5(data).hexdigest()[:10]
                size = len(data)
            rows.append((n, seq.group(1) if seq else "?", td.group(1) if td else "?",
                         seg, size, md5))
            print(f"hls/{n:<2} seq={rows[-1][1]:>6} td={rows[-1][2]} seg={seg} {size}B md5={md5}")
        except Exception as e:
            print(f"hls/{n:<2} ERR {type(e).__name__}: {e}")
    print("\n== 相同指纹分组（同一路流） ==")
    from collections import defaultdict
    g = defaultdict(list)
    for n, _s, _t, _seg, _sz, md5 in rows:
        if md5 != "-":
            g[md5].append(n)
    for md5, ns in g.items():
        if len(ns) > 1:
            print(f"  md5={md5}: hls {ns}  <- 同一路流")
    print("  （未列出的指纹唯一）")

if __name__ == "__main__":
    main()
