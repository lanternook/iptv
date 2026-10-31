#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_source.py —— 找源【备选方案】：零散直链源的批量发现 → 粗筛 → 手机精测 → 入库。

优先用 find_gateway.py（网关一个地址覆盖 17 个台，质量更高）。本脚本只在
「网关全挂、只剩直链」时用；搜索关键词偏向 tsfile/txiptv 这类直链特征。

流程（对应 docs/操作说明.md「找源方法」）：
  1. GitHub 代码搜索多个关键词，拿到一批含直播地址的仓库文件
  2. 拉文件内容，正则提取两类候选
       · 网关   IP:port + /newlive/live/hls/{N}/live.m3u8
       · 直链   http(s)://.../*.m3u8
  3. 本机粗筛（只判活：HTTP 200 + #EXTM3U），剔除死地址，减少手机端工作量
  4. 生成手机测速清单 output/phone_urls.txt（`标签|url`），交给 tools/phone_speed.sh
  5. 手机结果回灌 → output/found_gateway.txt / output/found_url.txt（按速率降序）

用法:
  python tools/find_source.py                      # 搜索 + 粗筛 + 生成手机清单
  python tools/find_source.py --pages 3            # 多翻几页
  python tools/find_source.py --keywords "a,b"     # 自定义关键词
  python tools/find_source.py --no-probe           # 跳过本机粗筛（本机没网/在代理后面时）
  python tools/find_source.py --ingest output/phone_result.txt   # 回灌手机结果

手机端（目标机同网，通常是湖北移动）:
  adb push tools/phone_speed.sh /data/local/tmp/
  adb push output/phone_urls_src.txt /data/local/tmp/urls.txt
  adb shell "sh /data/local/tmp/phone_speed.sh /data/local/tmp/urls.txt 3" > output/phone_result.txt

注意：本机若是电信而目标机是移动，本机测出来的速率没有参考价值，只用来判活。
"""
import argparse
import base64
import json
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

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 9) okhttp/3.12.0"}

DEFAULT_KEYWORDS = [
    "newlive/live/hls",
    "tsfile/live",
    "m3u8?key=txiptv",
    "newlive/live/hls/1/live.m3u8",
]

GW_RE = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3}:\d+)/newlive/live/hls/(\d+)/live\.m3u8")
URL_RE = re.compile(r"https?://[^\s\"'<>,，、]+?\.m3u8(?:\?[^\s\"'<>,，、]*)?")


# ---------- 1. 搜索 ----------
def search_code(keyword, pages):
    out = []
    for p in range(1, pages + 1):
        q = urllib.parse.quote(keyword)
        code, raw = call("GET", "/search/code?q=%s&per_page=30&page=%d" % (q, p))
        if code != 200:
            print("  搜索 HTTP %s（关键词 %s）" % (code, keyword))
            break
        try:
            items = json.loads(raw).get("items", [])
        except Exception:  # noqa: BLE001
            break
        for it in items:
            out.append((it["repository"]["full_name"], it["path"]))
        if len(items) < 30:
            break
    return out


def fetch_raw(repo, path):
    code, raw = call("GET", "/repos/%s/contents/%s" % (repo, urllib.parse.quote(path)))
    if code != 200:
        return ""
    try:
        d = json.loads(raw)
        return base64.b64decode(d.get("content", "")).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


# ---------- 2/3. 提取 + 粗筛 ----------
def probe_gateway(host, n=1, timeout=8):
    url = "http://%s/newlive/live/hls/%d/live.m3u8" % (host, n)
    try:
        r = DIRECT.open(urllib.request.Request(url, headers=UA), timeout=timeout)
        return "#EXTM3U" in r.read(4096).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return False


def probe_url(url, timeout=8):
    try:
        r = DIRECT.open(urllib.request.Request(url, headers=UA), timeout=timeout)
        body = r.read(8192).decode("utf-8", "replace")
        return "#EXTM3U" in body
    except Exception:  # noqa: BLE001
        return False


def collect(files, limit):
    """从文件内容里提取候选：返回 (网关 set, 直链 set)"""
    gws, urls = set(), set()
    for i, (repo, path) in enumerate(files, 1):
        txt = fetch_raw(repo, path)
        if i % 20 == 0:
            print("    拉取 %d/%d，累计网关 %d 直链 %d" % (i, len(files), len(gws), len(urls)))
        if not txt:
            continue
        for m in GW_RE.finditer(txt):
            gws.add(m.group(1))
        for m in URL_RE.finditer(txt):
            u = m.group(0)
            if "/newlive/live/hls/" in u:      # 网关类已单独处理
                continue
            urls.add(u)
        if len(gws) + len(urls) >= limit:
            break
    return gws, urls


# ---------- 5. 回灌 ----------
def ingest(result_path):
    gws, urls = [], []
    for raw in open(result_path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        p = s.split("|")
        if len(p) < 4:
            continue
        tag = p[0]
        try:
            mbps = float(p[1])
            nbytes = int(float(p[3]))
        except ValueError:
            continue
        if p[2] != "200" or nbytes < 100000:
            continue
        if tag.startswith("gw@"):
            gws.append((tag[3:], mbps))
        else:
            urls.append((tag, mbps))
    gws.sort(key=lambda x: -x[1])
    urls.sort(key=lambda x: -x[1])
    gw_out = os.path.join(ROOT, "output", "found_gateway.txt")
    url_out = os.path.join(ROOT, "output", "found_url.txt")
    with open(gw_out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# find_source.py 手机实测（目标机同网），按中位速率降序\n")
        for h, m in gws:
            f.write("%s  %.2f Mbps\n" % (h, m))
    with open(url_out, "w", encoding="utf-8", newline="\n") as f:
        for tag, m in urls:
            f.write("%s,%.2f Mbps\n" % (tag, m))
    print("网关 %d 个 -> %s" % (len(gws), gw_out))
    print("直链 %d 条 -> %s" % (len(urls), url_out))
    if gws:
        print("\n可并入 config/gateway_pool.txt（记得用抓帧确认编号方案）：")
        for h, m in gws[:10]:
            print("  %s  %.2f" % (h, m))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS))
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--max-urls", type=int, default=60, help="本机粗筛最多试多少条直链")
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--ingest")
    a = ap.parse_args()

    if a.ingest:
        ingest(a.ingest)
        return 0

    kws = [k.strip() for k in a.keywords.split(",") if k.strip()]
    files = []
    for k in kws:
        got = search_code(k, a.pages)
        print("关键词 %-28s 命中文件 %d" % (k, len(got)))
        files.extend(got)
    # 去重
    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    print("去重后文件 %d 个，开始拉内容…" % len(uniq))

    gws, urls = collect(uniq, a.limit)
    print("提取到网关 %d 个、直链 %d 条" % (len(gws), len(urls)))

    if not a.no_probe:
        print("本机粗筛（只判活，速率不作参考）…")
        gws = {h for h in gws if probe_gateway(h)}
        print("  网关存活 %d" % len(gws))
        cand = sorted(urls)[:a.max_urls]
        print("  直链粗筛 %d 条（共 %d 条，超出部分不试）" % (len(cand), len(urls)))
        keep = []
        for i, u in enumerate(cand, 1):
            ok = probe_url(u)
            if i % 10 == 0 or ok:
                print("    %d/%d %s %s" % (i, len(cand), "OK " if ok else "死 ", u[:70]))
            if ok:
                keep.append(u)
        urls = set(keep)
        print("  直链存活 %d" % len(urls))

    out = os.path.join(ROOT, "output", "phone_urls_src.txt")
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for h in sorted(gws):
            f.write("gw@%s|http://%s/newlive/live/hls/1/live.m3u8\n" % (h, h))
            n += 1
        for i, u in enumerate(sorted(urls)[:a.max_urls]):
            f.write("url%03d|%s\n" % (i, u))
            n += 1
    print("\n手机测速清单 %d 条 -> %s" % (n, out))
    print("下一步：")
    print('  adb push tools/phone_speed.sh /data/local/tmp/')
    print('  adb push output/phone_urls_src.txt /data/local/tmp/urls.txt')
    print('  adb shell "sh /data/local/tmp/phone_speed.sh /data/local/tmp/urls.txt 3" > output/phone_result.txt')
    print('  python tools/find_source.py --ingest output/phone_result.txt')
    return 0


if __name__ == "__main__":
    sys.exit(main())
