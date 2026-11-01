#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iptv_url_gen.py —— 直播源订阅地址生成 + 探测排序（仅标准库）

对 {user}/{repo}@{branch} 的 raw 地址生成 4 条候选（jsDelivr / ghgo / gh-proxy / 直连），
逐条探测（5s 超时、Range 取前 2KB、校验 #genre# 或 #EXTM3U），按响应时间排序写入
output/iptv_urls.txt，并打印「主地址 / 备用地址」。

用法:
    python tools/iptv_url_gen.py                      # 读取 tools/site.json
    python tools/iptv_url_gen.py --user your-github-user --repo iptv
    python tools/iptv_url_gen.py --user your-github-user --repo iptv --branch master --file output/user_result.txt
    python tools/iptv_url_gen.py --no-probe           # 只生成不探测
    python tools/iptv_url_gen.py --save-user your-github-user --save-repo iptv   # 记住参数

退出码: 0 至少 1 条通过; 1 全部失败; 2 参数错误
"""
import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE_CFG = os.path.join(HERE, "site.json")
OUT_FILE = os.path.join(ROOT, "output", "iptv_urls.txt")

PROXY = os.environ.get("IPTV_PROXY", "http://127.0.0.1:7897")
TIMEOUT = 5
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90 Mobile Safari/537.36"

# (名称, 模板) —— 2026-10-30 实测：jsDelivr / ghfast.top / gh-proxy.com 三条代理可用，
# 方案原定的 ghgo.xyz 已退化为 HTML 落地页（返回 200 但不是文件内容），故替换为 ghfast.top。
TEMPLATES = [
    ("jsDelivr CDN", "https://cdn.jsdelivr.net/gh/{user}/{repo}@{branch}/{file}"),
    ("ghfast.top", "https://ghfast.top/https://raw.githubusercontent.com/{user}/{repo}/{branch}/{file}"),
    ("gh-proxy.com", "https://gh-proxy.com/github.com/{user}/{repo}/raw/{branch}/{file}"),
    ("直连 raw", "https://raw.githubusercontent.com/{user}/{repo}/{branch}/{file}"),
]

MARKERS = ("#genre#", "#EXTM3U")


def load_cfg():
    if os.path.exists(SITE_CFG):
        try:
            with open(SITE_CFG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cfg(d):
    with open(SITE_CFG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def build_urls(user, repo, branch, path):
    out = []
    for name, tpl in TEMPLATES:
        out.append((name, tpl.format(user=user, repo=repo, branch=branch, file=path)))
    return out


def make_opener(use_proxy=True):
    handlers = []
    if use_proxy and PROXY:
        handlers.append(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def probe(url, use_proxy=True):
    """返回 (ok, elapsed_ms, 说明)。"""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", UA)
    req.add_header("Range", "bytes=0-2047")
    req.add_header("Cache-Control", "no-cache")
    t0 = time.time()
    try:
        with make_opener(use_proxy).open(req, timeout=TIMEOUT) as r:
            body = r.read(2048)
            ms = int((time.time() - t0) * 1000)
            text = body.decode("utf-8", "replace")
            hit = next((m for m in MARKERS if m in text), None)
            if hit:
                return True, ms, "OK(%s, HTTP %s)" % (hit, r.status)
            return False, ms, "内容无 %s 标记(HTTP %s)" % ("/".join(MARKERS), r.status)
    except urllib.error.HTTPError as e:
        return False, int((time.time() - t0) * 1000), "HTTP %s" % e.code
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return False, int((time.time() - t0) * 1000), "网络失败: %s" % getattr(e, "reason", e)
    except Exception as e:  # noqa: BLE001
        return False, int((time.time() - t0) * 1000), "%s: %s" % (type(e).__name__, e)


def count_channels(path_on_disk):
    """可选：本地已有结果文件时统计频道数。"""
    if not path_on_disk or not os.path.exists(path_on_disk):
        return None
    try:
        with open(path_on_disk, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        names = set()
        for line in txt.splitlines():
            line = line.strip()
            if not line or "," not in line or line.startswith("#"):
                continue
            name, url = line.split(",", 1)
            if url.strip().lower().startswith(("http", "rtp", "rtsp", "udp")):
                names.add(name.strip())
        return len(names)
    except Exception:
        return None


def main():
    cfg = load_cfg()
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--user", default=cfg.get("user") or os.environ.get("IPTV_USER") or "")
    ap.add_argument("--repo", default=cfg.get("repo", "iptv"))
    ap.add_argument("--branch", default=cfg.get("branch", "master"))
    ap.add_argument("--file", default=cfg.get("file", "output/user_result.txt"))
    ap.add_argument("--no-proxy", action="store_true", help="探测时不用本机代理（模拟播放器直连环境）")
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--save-user")
    ap.add_argument("--save-repo")
    args = ap.parse_args()

    if args.save_user or args.save_repo:
        if args.save_user:
            cfg["user"] = args.save_user
        if args.save_repo:
            cfg["repo"] = args.save_repo
        cfg["branch"] = args.branch
        cfg["file"] = args.file
        save_cfg(cfg)
        print("已保存参数到 tools/site.json: %s" % json.dumps(cfg, ensure_ascii=False))
        if not args.user:
            args.user = cfg.get("user", "")

    if not args.user:
        print("错误: 缺少 GitHub 用户名，用 --user 指定或用 --save-user 记住", file=sys.stderr)
        return 2

    urls = build_urls(args.user, args.repo, args.branch, args.file)
    use_proxy = not args.no_proxy
    rows = []
    for name, url in urls:
        if args.no_probe:
            rows.append({"name": name, "url": url, "ok": None, "ms": None, "note": "未探测"})
            continue
        ok, ms, note = probe(url, use_proxy)
        rows.append({"name": name, "url": url, "ok": ok, "ms": ms, "note": note})
        print("[%s] %-13s %5sms  %s" % ("通过" if ok else "失败", name, ms, note))

    ok_rows = sorted([r for r in rows if r["ok"]], key=lambda r: r["ms"])
    fail_rows = [r for r in rows if r["ok"] is False]

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("# 直播源订阅地址（生成时间 %s）\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("# 目标: %s/%s@%s/%s\n" % (args.user, args.repo, args.branch, args.file))
        f.write("# 探测: 超时%ss, 校验 %s, 代理=%s\n\n" % (TIMEOUT, "/".join(MARKERS), "开" if use_proxy else "关"))
        f.write("%-4s %-14s %-8s %s\n" % ("排名", "通道", "耗时", "地址"))
        for i, r in enumerate(ok_rows, 1):
            f.write("%-4d %-14s %-8s %s\n" % (i, r["name"], "%dms" % r["ms"], r["url"]))
        for r in fail_rows:
            f.write("%-4s %-14s %-8s %s   # %s\n" % ("-", r["name"], "-", r["url"], r["note"]))
        for r in rows:
            if r["ok"] is None:
                f.write("%-4s %-14s %-8s %s   # %s\n" % ("?", r["name"], "-", r["url"], r["note"]))
        f.write("\n")
        if ok_rows:
            f.write("主地址: %s\n" % ok_rows[0]["url"])
            for r in ok_rows[1:]:
                f.write("备用地址: %s\n" % r["url"])
        elif args.no_probe:
            f.write("主地址(未探测, 按模板顺序): %s\n" % rows[0]["url"])
            for r in rows[1:]:
                f.write("备用地址(未探测): %s\n" % r["url"])
        else:
            f.write("主地址: （无可用通道）\n")

    print("-" * 60)
    if ok_rows:
        print("主地址: %s" % ok_rows[0]["url"])
        for r in ok_rows[1:]:
            print("备用地址: %s" % r["url"])
        print("通过 %d/%d 条，结果已写入 %s" % (len(ok_rows), len(rows), OUT_FILE))
        return 0
    if args.no_probe:
        print("已生成 %d 条候选（未探测），写入 %s" % (len(rows), OUT_FILE))
        return 0
    print("全部通道探测失败，检查仓库是否已跑过 Actions、分支名/文件名是否正确")
    return 1


if __name__ == "__main__":
    sys.exit(main())
