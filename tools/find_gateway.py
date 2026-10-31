#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_gateway.py —— 找源主入口：发现 / 验证 / 排序同结构 IPTV 转发网关。

为什么优先找网关：`IP:port/newlive/live/hls/{N}/live.m3u8` 一个地址就覆盖 17 个央视台，
质量和稳定性都高于零散直链；直链源只作备选（见 find_source.py）。

流程（每步都有进度输出）：
  [1/5] GitHub 代码搜索（多关键词、逐页）
  [2/5] 拉文件内容，正则提取 host:port
  [3/5] 去重（默认跳过池里已有的）
  [4/5] 串行验证（拉 hls/1 看 #EXTM3U，再拉首个分片算速率）
  [5/5] 按速率降序写 config/gateway_pool.txt

本机若不是目标机同网（本机电信、目标机移动），速率**排序不可用**，只能判活。
精测走手机（目标机同网）：
    python tools/find_gateway.py --phone
    adb push tools/phone_speed.sh /data/local/tmp/
    adb push output/phone_urls.txt /data/local/tmp/urls.txt
    adb shell "sh /data/local/tmp/phone_speed.sh /data/local/tmp/urls.txt 3" > output/phone_result.txt
    python tools/find_gateway.py --ingest output/phone_result.txt

用法:
    python tools/find_gateway.py                  # 搜索 + 验证 + 写池
    python tools/find_gateway.py --verify-only    # 只复验池里已有的
    python tools/find_gateway.py --pages 3        # 多翻页
    python tools/find_gateway.py --all            # 不跳过池里已有的
    python tools/find_gateway.py --phone          # 只生成手机测速清单
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

PAT = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3}:\d+)/[^\s\"',]*?/hls/(\d+)/live\.m3u8")
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 9) okhttp/3.12.0"}

DEFAULT_KEYWORDS = ["newlive/live/hls", "newlive/live/hls/1/live.m3u8"]

T0 = time.time()


def log(msg=""):
    print("[%5.1fs] %s" % (time.time() - T0, msg) if msg else "")


def bar(i, total):
    return "%d/%d" % (i, total)


# ---------- 搜索 ----------
def search_code(keyword, pages):
    """返回 [(repo, path)]。"""
    out = []
    for p in range(1, pages + 1):
        q = urllib.parse.quote(keyword)
        code, raw = call("GET", "/search/code?q=%s&per_page=30&page=%d" % (q, p))
        if code != 200:
            log("    搜索 HTTP %s（关键词 %s，第 %d 页），跳过" % (code, keyword, p))
            break
        try:
            items = json.loads(raw).get("items", [])
        except Exception:  # noqa: BLE001
            log("    返回非 JSON，跳过")
            break
        out.extend((it["repository"]["full_name"], it["path"]) for it in items)
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


# ---------- 验证 ----------
def probe(host_port, n=1, timeout=8):
    """拉 m3u8 + 首个分片，返回 (ok, mbps)。"""
    url = "http://%s/newlive/live/hls/%d/live.m3u8" % (host_port, n)
    try:
        body = DIRECT.open(urllib.request.Request(url, headers=UA), timeout=timeout
                           ).read().decode("utf-8", "replace")
        if "#EXTM3U" not in body:
            return False, 0.0
        seg = [l.strip() for l in body.splitlines() if l.strip() and not l.startswith("#")]
        if not seg:
            return False, 0.0
        t0 = time.time()
        data = DIRECT.open(urllib.request.Request(
            "http://%s/newlive/live/hls/%d/%s" % (host_port, n, seg[0]), headers=UA),
            timeout=25).read()
        el = max(time.time() - t0, 0.01)
        return True, len(data) * 8 / el / 1e6
    except Exception:  # noqa: BLE001
        return False, 0.0


def load_pool(path):
    hosts = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                hosts.add(s.split()[0])
    return hosts


def write_pool(path, rows, note="", annot=None):
    """写池文件。annot 保留已有网关的「编号方案/说明」，避免复验时把人工确认的信息冲掉。"""
    annot = annot or {}
    lines = ["# 同类 IPTV 转发网关池（路径模板 /newlive/live/hls/{N}/live.m3u8）",
             "# 生成：find_gateway.py %s%s" % (time.strftime("%Y-%m-%d %H:%M"), note),
             "# 格式：host:port  速率Mbps  编号方案  说明（编号方案需抓帧确认，? = 未确认）"]
    for h, m in rows:
        scheme, desc = annot.get(h, ("?", "待抓帧确认编号"))
        lines.append("%s  %.2f  %s  %s" % (h, m, scheme, desc))
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def load_annot(path):
    """读已有池文件里的 (编号方案, 说明)。"""
    d = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split()
            if len(p) >= 4:
                d[p[0]] = (p[2], " ".join(p[3:]))
    return d


# ---------- 手机精测 ----------
def emit_phone(hosts, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for h in sorted(hosts):
            f.write("gw@%s|http://%s/newlive/live/hls/1/live.m3u8\n" % (h, h))
    log("手机测速清单 %d 条 -> %s" % (len(hosts), path))
    log("  adb push tools/phone_speed.sh /data/local/tmp/")
    log("  adb push %s /data/local/tmp/urls.txt" % path)
    log('  adb shell "sh /data/local/tmp/phone_speed.sh /data/local/tmp/urls.txt 3" > output/phone_result.txt')
    log("  python tools/find_gateway.py --ingest output/phone_result.txt")


def ingest(result_path, pool_path, note):
    rows = []
    for raw in open(result_path, encoding="utf-8", errors="replace"):
        p = raw.strip().split("|")
        if len(p) < 4 or not p[0].startswith("gw@"):
            continue
        try:
            mbps = float(p[1])
            nbytes = int(float(p[3]))
        except ValueError:
            continue
        if p[2] != "200" or nbytes < 100000:
            continue
        rows.append((p[0][3:], mbps))
    rows.sort(key=lambda x: -x[1])
    if not rows:
        log("结果里没有可用网关（检查清单格式：gw@host:port|url）")
        return 1
    write_pool(pool_path, rows, " 手机实测回灌", load_annot(pool_path))
    log("可用网关 %d 个，已写入 %s" % (len(rows), pool_path))
    for h, m in rows[:10]:
        log("  %-24s %.2f Mbps" % (h, m))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS))
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--verify-only", action="store_true", help="只复验池里已有的，不搜索")
    ap.add_argument("--all", action="store_true", help="不跳过池里已有的候选")
    ap.add_argument("--phone", action="store_true", help="只生成手机测速清单，不验证")
    ap.add_argument("--ingest", help="回灌手机测速结果")
    ap.add_argument("--out", default=os.path.join(ROOT, "config", "gateway_pool.txt"))
    a = ap.parse_args()

    if a.ingest:
        return ingest(a.ingest, a.out, " 手机实测回灌")

    known = load_pool(a.out)
    log("已有网关 %d 个（%s）" % (len(known), os.path.basename(a.out)))

    # ---- 1/5 搜索 ----
    hosts = set()
    if a.verify_only:
        log("[1/5] 跳过搜索，只复验已有")
        hosts = set(known)
    else:
        log("[1/5] GitHub 代码搜索")
        kws = [k.strip() for k in a.keywords.split(",") if k.strip()]
        files = []
        for i, kw in enumerate(kws, 1):
            got = search_code(kw, a.pages)
            log("  %s 关键词「%s」命中文件 %d" % (bar(i, len(kws)), kw, len(got)))
            files.extend(got)
        seen, uniq = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                uniq.append(f)
        log("[2/5] 去重后 %d 个文件，逐个拉内容提取" % len(uniq))

        for i, (repo, path) in enumerate(uniq, 1):
            txt = fetch_raw(repo, path)
            found = set(m.group(1) for m in PAT.finditer(txt))
            if found:
                log("  %s %-38s +%d 个网关" % (bar(i, len(uniq)), repo[:38], len(found)))
            hosts |= found
            if i % 20 == 0:
                log("  ... 进度 %s，累计候选 %d" % (bar(i, len(uniq)), len(hosts)))
        log("  提取完成：%d 个不同 host:port" % len(hosts))

    if not hosts:
        log("没有候选，退出（检查代理/令牌，或换关键词）")
        return 1

    # ---- 3/5 去重 ----
    if not a.all and not a.verify_only:
        fresh = hosts - known
        log("[3/5] 去掉池里已有的 %d 个，剩 %d 个新候选" % (len(hosts) - len(fresh), len(fresh)))
        if not fresh:
            log("  没有新候选，改为复验全部")
            fresh = hosts
        hosts = fresh
    else:
        log("[3/5] 不做复用过滤，候选 %d 个" % len(hosts))

    if a.phone:
        emit_phone(hosts, os.path.join(ROOT, "output", "phone_urls.txt"))
        return 0

    # ---- 4/5 验证 ----
    log("[4/5] 串行验证（每个约 3~10 秒，共 %d 个）" % len(hosts))
    ok = []
    for i, h in enumerate(sorted(hosts), 1):
        good, mbps = probe(h)
        log("  %s %-24s %s" % (bar(i, len(hosts)), h,
                               ("OK %.2f Mbps" % mbps) if good else "失效"))
        if good:
            ok.append((h, mbps))

    if not ok:
        log("全部失效。旧池文件保留不动，可改 --phone 用手机网络复测")
        return 1

    # ---- 5/5 写池 ----
    merged = dict(ok)
    if a.verify_only or a.all:
        for line in open(a.out, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                merged.setdefault(s.split()[0], 0.0)
    rows = sorted(((h, m) for h, m in merged.items() if m > 0), key=lambda x: -x[1])
    write_pool(a.out, rows, " 本机实测，速率仅供参考", load_annot(a.out))
    log("[5/5] 可用 %d 个，已写入 %s" % (len(rows), a.out))
    for h, m in rows[:10]:
        log("  %-24s %.2f Mbps" % (h, m))
    log("")
    log("提醒：新网关的编号方案必须抓帧确认后才能用于排序")
    log("  python tools/grab_frames.py http://<host:port> 1,6,10,17 tmp/frames")
    log("  确认后跑 python tools/reorder_gateways.py 重排 curated.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
