#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_gateway.py —— 发现 / 验证同结构的 IPTV 转发网关。

湖北移动的 `120.40.39.246:352/newlive/live/hls/{N}/live.m3u8` 这类网关，
结构相同的一批散落在社区源里。本脚本：
  1. 用 GitHub 代码搜索找含该路径的文件
  2. 拉取文件内容，正则提取 host:port
  3. 逐个验证（能拉到 hls/1 且是 #EXTM3U）
  4. 测速排序，写入 config/gateway_pool.txt

用法:
    python tools/find_gateway.py                 # 搜索 + 验证
    python tools/find_gateway.py --verify-only   # 只验证 gateway_pool.txt 里已有的
"""
import argparse
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gh_api import call  # noqa: E402

PAT = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3}:\d+)/[^\s\"',]*?/hls/(\d+)/live\.m3u8")
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def search_code(keyword="newlive/live/hls", pages=2):
    """返回 [(repo, path)]，用 GitHub 代码搜索。"""
    out = []
    for p in range(1, pages + 1):
        q = urllib.parse.quote(keyword)
        code, raw = call("GET", "/search/code?q=%s&per_page=30&page=%d" % (q, p))
        if code != 200:
            print("  搜索失败 HTTP %s（可能需要 token 权限）" % code)
            break
        import json
        for it in json.loads(raw).get("items", []):
            out.append((it["repository"]["full_name"], it["path"]))
    return out


def fetch_raw(repo, path):
    """拉文件内容（走 Contents API，兼容中文路径）。"""
    code, raw = call("GET", "/repos/%s/contents/%s" % (repo, urllib.parse.quote(path)))
    if code != 200:
        return ""
    import base64
    import json
    try:
        d = json.loads(raw)
        return base64.b64decode(d.get("content", "")).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def probe(host_port, n=1, timeout=8):
    """验证网关能否拉到指定频道号，返回 (ok, mbps)。"""
    url = "http://%s/newlive/live/hls/%d/live.m3u8" % (host_port, n)
    try:
        r = DIRECT.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout)
        body = r.read().decode("utf-8", "replace")
        if "#EXTM3U" not in body:
            return False, 0.0
        seg = [l.strip() for l in body.splitlines() if l.strip() and not l.startswith("#")]
        if not seg:
            return False, 0.0
        t0 = time.time()
        seg_url = "http://%s/newlive/live/hls/%d/%s" % (host_port, n, seg[0])
        data = DIRECT.open(urllib.request.Request(seg_url, headers={"User-Agent": "Mozilla/5.0"}),
                           timeout=25).read()
        el = max(time.time() - t0, 0.01)
        return True, len(data) * 8 / el / 1e6
    except Exception:  # noqa: BLE001
        return False, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(ROOT, "config", "gateway_pool.txt"))
    a = ap.parse_args()

    hosts = set()
    if os.path.exists(a.out):
        for line in open(a.out, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                hosts.add(s.split()[0])
        print("已有 %d 个候选" % len(hosts))

    if not a.verify_only:
        print("GitHub 代码搜索...")
        files = search_code(pages=a.pages)
        print("  命中 %d 个文件，开始提取" % len(files))
        for i, (repo, path) in enumerate(files, 1):
            txt = fetch_raw(repo, path)
            found = set(m.group(1) for m in PAT.finditer(txt))
            if found:
                print("  %-40s +%d" % (repo[:40], len(found)))
            hosts |= found
            if i % 10 == 0:
                print("    ...%d/%d" % (i, len(files)))
        print("提取到 %d 个不同 host:port" % len(hosts))

    # 验证：串行，避免被当成扫描
    ok = []
    print("\n验证（串行，每个约 3 秒）：")
    for h in sorted(hosts):
        good, mbps = probe(h)
        print("  %-24s %s" % (h, "OK %.2f Mbps" % mbps if good else "失效"))
        if good:
            ok.append((mbps, h))

    ok.sort(reverse=True)
    lines = ["# 同类 IPTV 转发网关（find_gateway.py 生成，%s）" % time.strftime("%Y-%m-%d %H:%M"),
             "# 格式：host:port  可用的按测速降序，路径模板 /newlive/live/hls/{N}/live.m3u8"]
    lines += ["%s  # %.2f Mbps" % (h, m) for m, h in ok]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n可用 %d 个，已写入 %s" % (len(ok), a.out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
