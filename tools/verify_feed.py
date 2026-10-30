#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_feed.py —— 用播放器 UA 复测订阅地址，并校验文件格式。

用途：FongMi 报"更新失败"时，区分是「镜像拒绝播放器 UA」还是「文件内容不合法」。

用法: python tools/verify_feed.py [--file output/curated.txt]
"""
import argparse
import hashlib
import os
import re
import socket
import sys
import urllib.error
import urllib.request

PROXY = os.environ.get("IPTV_PROXY", "http://127.0.0.1:7897")
UAS = {
    "okhttp(FongMi)": "okhttp/3.15",
    "ExoPlayer": "ExoPlayerLib/2.19.1",
    "Mozilla": "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36",
}
USER, REPO, BRANCH, FILE = "lanternook", "iptv", "main", "output/curated.txt"
MIRRORS = [
    ("raw", "https://raw.githubusercontent.com/%s/%s/%s/%s" % (USER, REPO, BRANCH, FILE)),
    ("gh-proxy", "https://gh-proxy.com/github.com/%s/%s/raw/%s/%s" % (USER, REPO, BRANCH, FILE)),
    ("ghfast", "https://ghfast.top/https://raw.githubusercontent.com/%s/%s/%s/%s" % (USER, REPO, BRANCH, FILE)),
    ("jsDelivr", "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (USER, REPO, BRANCH, FILE)),
]


def fetch(url, ua, use_proxy=False):
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY} if use_proxy else {}))
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with op.open(req, timeout=12) as r:
            body = r.read()
            return r.status, body, r.headers.get("Content-Type"), r.headers.get("Content-Length")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300], e.headers.get("Content-Type"), None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return 0, str(getattr(e, "reason", e)).encode(), None, None


def check_format(path):
    raw = open(path, "rb").read()
    print("\n[格式校验] %s" % path)
    print("  大小 %d 字节，BOM: %s" % (len(raw), "有" if raw[:3] == b"\xef\xbb\xbf" else "无"))
    try:
        text = raw.decode("utf-8")
        print("  UTF-8 解码: OK")
    except UnicodeDecodeError as e:
        print("  UTF-8 解码失败: %s" % e)
        return
    lines = text.splitlines()
    bad, longline, dup = [], 0, {}
    cur = None
    for i, l in enumerate(lines, 1):
        if not l.strip():
            continue
        if l.count(",") > 1 and "#genre#" not in l:
            # 台名,url 只应有一个分隔逗号；URL 内含逗号会让解析器错位
            head, rest = l.split(",", 1)
            if rest.lower().startswith("http"):
                bad.append((i, "URL 内含逗号", l[:80]))
        if len(l) > 1000:
            longline += 1
        if "#genre#" in l:
            cur = l.split(",")[0]
            continue
        if "," in l:
            name, url = l.split(",", 1)
            if not url.lower().startswith(("http", "rtmp", "rtsp")):
                bad.append((i, "URL 不合法", l[:80]))
            dup[(cur, name, url)] = dup.get((cur, name, url), 0) + 1
    print("  行数 %d，超长行(>1000字符) %d，重复行 %d" % (
        len(lines), longline, sum(1 for v in dup.values() if v > 1)))
    if bad:
        print("  问题行 %d 条:" % len(bad))
        for i, why, sample in bad[:8]:
            print("    第%d行 %s: %s" % (i, why, sample))
    else:
        print("  格式校验通过")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="output/curated.txt")
    ap.add_argument("--proxy", action="store_true", help="拉取时经本机代理（本机访问 GitHub 需要时）")
    a = ap.parse_args()

    local = hashlib.md5(open(a.file, "rb").read()).hexdigest()
    check_format(a.file)
    print("\n[地址探测] 本地 md5 = %s" % local)
    print("%-16s %-16s %-6s %-9s %-10s %s" % ("镜像", "UA", "HTTP", "大小", "md5匹配", "备注"))
    for name, url in MIRRORS:
        for ua_name, ua in UAS.items():
            code, body, ctype, clen = fetch(url, ua, a.proxy)
            md5 = hashlib.md5(body).hexdigest() if code == 200 else "-"
            match = "✓" if md5 == local else ("✗" if code == 200 else "-")
            note = ""
            if code == 200 and b"<html" in body[:200].lower():
                note = "返回HTML非纯文本"
            print("%-16s %-16s %-6s %-9d %-10s %s" % (
                name, ua_name, code or "ERR", len(body), match, note))
    print("\n提示: md5 不匹配且内容为 HTML → 该镜像对该 UA 返回错误页，播放器会判为更新失败")


if __name__ == "__main__":
    sys.exit(main())
