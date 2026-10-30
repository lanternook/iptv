#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验订阅源可用性（仅标准库）。用法: python tools/check_subs.py [文件]"""
import socket
import sys
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7897"
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"

SUBS = [
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv4.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
    "https://raw.githubusercontent.com/zbefine/iptv/main/iptv.m3u",
]


def main():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    for u in SUBS:
        t0 = time.time()
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-4095"})
            with op.open(req, timeout=8) as r:
                body = r.read(4096).decode("utf-8", "replace")
            ms = int((time.time() - t0) * 1000)
            ok = "#EXTM3U" in body or "#genre#" in body
            n = body.count("CCTV")
            print("%-4s %5dms CCTV命中%-3d %s" % ("OK" if ok else "BAD", ms, n, u))
        except urllib.error.HTTPError as e:
            print("%-4s %5dms            %s  (HTTP %s)" % ("ERR", int((time.time() - t0) * 1000), u, e.code))
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            print("%-4s %5dms            %s  (%s)" % ("ERR", int((time.time() - t0) * 1000), u, getattr(e, "reason", e)))


if __name__ == "__main__":
    main()
