#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测xx移动转发网关：连通性、播放列表结构、可能的频道清单接口。"""
import urllib.request, socket, ssl, sys

GW = "http://120.40.39.246:352"
TPL = GW + "/newlive/live/hls/{n}/live.m3u8"

def get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/3.12.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def main():
    print("== 单频道播放列表结构 (hls/1,7,8,10,11) ==")
    for n in (1, 7, 8, 10, 11):
        try:
            st, body = get(TPL.format(n=n))
            txt = body.decode("utf-8", "replace")
            lines = [l for l in txt.splitlines() if l.strip()]
            print(f"hls/{n}: HTTP {st}, {len(body)}B, {len(lines)}行")
            for l in lines[:6]:
                print("   ", l[:120])
        except Exception as e:
            print(f"hls/{n}: ERR {type(e).__name__}: {e}")
    print("\n== 尝试常见频道清单/接口 ==")
    for p in ("/", "/index", "/list", "/channel", "/channels", "/api", "/iptv",
              "/newlive", "/newlive/live", "/newlive/index", "/live.m3u", "/tv.m3u"):
        try:
            st, body = get(GW + p, timeout=6)
            head = body[:200].decode("utf-8", "replace").replace("\n", " ")
            print(f"{p}: HTTP {st}, {len(body)}B | {head}")
        except Exception as e:
            print(f"{p}: ERR {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
