#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_speed.py —— 只测"现有订阅里的线路"，不做建池、不做合并、不推送。

给"与电视同网络的测速机"用：拿当前 curated.txt 逐条测，产出
  1) measured.txt  仍可用的线路（保持原分组与顺序）
  2) report.tsv    全部线路的实测结果（台名 / Mbps / 备注 / URL）

用法:
    python check_speed.py                      # 测本地 curated.txt
    python check_speed.py --pull               # 先从 GitHub 拉最新再测（镜像自动回退）
    python check_speed.py --src output/curated.txt --min-mbps 1.5
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
# 在项目里是 tools/ 子目录；单独拷到别处（交接包）时 HERE 就是根
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
sys.path.insert(0, HERE)
from local_speedtest import measure, log, fetch_source  # noqa: E402


def default_curated():
    p = os.path.join(ROOT, "output", "curated.txt")
    if os.path.exists(p):
        return p
    return os.path.join(ROOT, "curated.txt")


def parse(path):
    """返回 [(组名, [(台名, url), ...]), ...]，保持原顺序。"""
    groups, cur = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            groups.append((cur, []))
            continue
        if "," in s and cur is not None:
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")) and "example.com" not in u:
                groups[-1][1].append((n.strip(), u))
    return groups


def pull_remote(dest):
    """从 GitHub 拉最新 curated.txt（镜像自动回退），失败则保留本地。"""
    cfg_path = os.path.join(ROOT, "config", "publish.json")
    user, repo, branch = "lanternook", "iptv", "main"
    if os.path.exists(cfg_path):
        import json
        c = json.load(open(cfg_path, encoding="utf-8"))
        user, repo, branch = c.get("user", user), c.get("repo", repo), c.get("branch", branch)
    url = "https://raw.githubusercontent.com/%s/%s/%s/output/curated.txt" % (user, repo, branch)
    try:
        text, mirror = fetch_source(url)
        if text and "#genre#" in text:
            open(dest, "w", encoding="utf-8").write(text)
            log("已拉取远端最新订阅（%s）: %d 字节" % (mirror, len(text)))
            return True
    except Exception as e:  # noqa: BLE001
        log("拉取远端失败（%s），改用本地文件" % type(e).__name__)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="要体检的订阅文件（默认自动找 output/curated.txt 或同目录 curated.txt）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--min-mbps", type=float, default=0.1,
                    help="低于此值判为死链（体检只判存活，不评画质；死链是 0.00）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--pull", action="store_true", help="先从 GitHub 拉最新订阅再测")
    ap.add_argument("--serial-host", action="append", default=["120.40.39.246"],
                    help="这些 host 的线路串行测（网关并发会被限流误判）；可多次")
    a = ap.parse_args()

    if not a.src:
        a.src = default_curated()
    if a.pull:
        pull_remote(a.src)
    if not os.path.exists(a.src):
        log("找不到订阅文件: %s" % a.src)
        return 2

    groups = parse(a.src)
    flat = [(n, u) for _g, items in groups for n, u in items]
    log("体检 %s：%d 个分组，%d 条线路" % (os.path.basename(a.src), len(groups), len(flat)))
    log("测速期间不要看视频或下载，否则结果偏低")
    log("-" * 56)

    t0 = time.time()
    results = {}
    done = 0

    def record(it, mbps, note):
        nonlocal done
        results[(it[0], it[1])] = (mbps, note)
        done += 1
        if done % 25 == 0 or done == len(flat):
            ok = sum(1 for v in results.values() if v[0] >= a.min_mbps)
            log("  进度 %d/%d  可用 %d  已用 %.0fs" % (done, len(flat), ok, time.time() - t0))

    # 网关类 host 串行测：单 IP 转发服务，并发会被限流而误判为死链
    serial = [it for it in flat if any(h in it[1] for h in a.serial_host)]
    parallel = [it for it in flat if it not in set(serial)]
    if serial:
        log("  串行测 %d 条（网关类，避免并发限流误判）" % len(serial))
        for it in serial:
            try:
                _n, _u, mbps, note = measure(it, a.seconds, None)
            except Exception as e:  # noqa: BLE001
                mbps, note = 0.0, type(e).__name__
            record(it, mbps, note)

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(measure, it, a.seconds, None): it for it in parallel}
        for fut in futs:
            it = futs[fut]
            try:
                _n, _u, mbps, note = fut.result()
            except Exception as e:  # noqa: BLE001
                mbps, note = 0.0, type(e).__name__
            record(it, mbps, note)

    # 输出：可用的保持原顺序；报告写全部
    lines, report = [], ["# 台名\tMbps\t备注\tURL"]
    ok_total = 0
    dead_ch = []
    for gname, items in groups:
        kept = []
        for n, u in items:
            mbps, note = results.get((n, u), (0.0, "未测"))
            report.append("%s\t%.2f\t%s\t%s" % (n, mbps, note, u))
            if mbps >= a.min_mbps:
                kept.append((n, u))
        if kept:
            lines.append("%s,#genre#" % gname)
            lines.extend("%s,%s" % (n, u) for n, u in kept)
            ok_total += len(kept)
        dead = {n for n, _u in items} - {n for n, _u in kept}
        dead_ch.extend(sorted(dead))

    base_dir = os.path.dirname(a.src) or "."
    if not a.out:
        a.out = os.path.join(base_dir, "measured.txt")
    if not a.report:
        a.report = os.path.join(base_dir, "report.tsv")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open(a.report, "w", encoding="utf-8").write("\n".join(report) + "\n")

    log("-" * 56)
    log("可用 %d / %d 条，耗时 %.0f 秒" % (ok_total, len(flat), time.time() - t0))
    if dead_ch:
        log("完全失效的台（%d）: %s" % (len(dead_ch), ",".join(dead_ch)))
    log("已写入 %s" % a.out)
    log("        %s" % a.report)
    return 0 if ok_total else 1


if __name__ == "__main__":
    sys.exit(main())
