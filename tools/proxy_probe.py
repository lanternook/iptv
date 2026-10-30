#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量探测 GitHub 加速前缀可用性（仅标准库）。

用法: python tools/proxy_probe.py [--no-proxy]
目标文件默认取一个公开 m3u 作样本，校验返回体是否含 #EXTM3U。
"""
import socket
import sys
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7897"
SAMPLE = "raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u"
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"

# 前缀模板，{u} 为 raw 路径（无 scheme）
CANDS = [
    ("jsDelivr", "https://cdn.jsdelivr.net/gh/YueChan/Live@main/IPTV.m3u"),
    ("ghgo.xyz", "https://ghgo.xyz/" + SAMPLE),
    ("gh-proxy.com", "https://gh-proxy.com/github.com/YueChan/Live/raw/main/IPTV.m3u"),
    ("ghfast.top", "https://ghfast.top/https://" + SAMPLE),
    ("ghproxy.net", "https://ghproxy.net/https://" + SAMPLE),
    ("ghproxy.cc", "https://ghproxy.cc/https://" + SAMPLE),
    ("gh.llkk.cc", "https://gh.llkk.cc/https://" + SAMPLE),
    ("hub.gitmirror.com", "https://hub.gitmirror.com/https://" + SAMPLE),
    ("gitproxy.click", "https://gitproxy.click/https://" + SAMPLE),
    ("gh.xxooo.cf", "https://gh.xxooo.cf/https://" + SAMPLE),
    ("raw 直连", "https://" + SAMPLE),
]


def main():
    use_proxy = "--no-proxy" not in sys.argv
    handlers = [urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})] if use_proxy else [urllib.request.ProxyHandler({})]
    op = urllib.request.build_opener(*handlers)
    print("模式: %s" % ("经本机代理" if use_proxy else "无代理(模拟直连)"))
    for name, url in CANDS:
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-1023"})
            with op.open(req, timeout=6) as r:
                body = r.read(1024).decode("utf-8", "replace")
            ms = int((time.time() - t0) * 1000)
            ok = "#EXTM3U" in body
            print("%-20s %-4s %5dms  %s" % (name, "OK" if ok else "BAD", ms, "" if ok else repr(body[:60])))
        except urllib.error.HTTPError as e:
            print("%-20s %-4s %5dms  HTTP %s" % (name, "ERR", int((time.time() - t0) * 1000), e.code))
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            print("%-20s %-4s %5dms  %s" % (name, "ERR", int((time.time() - t0) * 1000), getattr(e, "reason", e)))


if __name__ == "__main__":
    main()
