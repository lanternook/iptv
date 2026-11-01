#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline.py —— 日常维护入口。核心是"体检 + 换血"，不是重建。

三种模式:
    python tools/pipeline.py
        体检本机现有订阅 → 换掉失效线路 → 推送（约 2~3 分钟）

    python tools/pipeline.py --apply D:/measured.txt
        用测速机（与电视同网络的机器）跑出来的结果换血 → 推送（约 10 秒）
        测速机上跑的是 check_speed.py，产出 measured.txt

    python tools/pipeline.py --rebuild
        全量重建：重新抓订阅源建池并全量测速（5~10 分钟，偶尔用）

公共选项: --no-push 只生成不推送 / --dry 只预览不写文件
"""
import argparse
import json
import locale
import os
import subprocess
import sys
import time
import urllib.request

# 控制台/重定向遇到 GBK 无法编码的字符（如 emoji）时降级，避免崩溃
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass

ENCODING = locale.getpreferredencoding(False) or "utf-8"   # Windows 中文=cp936

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

MERGE_ARGS = ["--drop-group", "凤凰频道", "--drop-group", "广东频道",
              "--move", "广州综合=卫视频道"]
MIN_KEEP = 20


def log(msg=""):
    print(msg, flush=True)


def step(n, total, title):
    log("")
    log("=" * 62)
    log("  [%d/%d] %s" % (n, total, title))
    log("=" * 62)


def run(cmd, logfile, echo_keys=()):
    log("  $ " + " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    t0 = time.time()
    # 子进程在 Windows 下按系统代码页（GBK）输出，必须按同一编码解码，否则日志乱码
    p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (p.stdout or b"").decode(ENCODING, errors="replace")
    with open(logfile, "a", encoding="utf-8") as f:
        f.write("\n$ " + " ".join(cmd) + "\n")
        f.write(out)
        f.write("\n[exit %d]\n" % p.returncode)
    for line in out.splitlines():
        if any(k in line for k in echo_keys):
            log("  " + line.strip())
    log("  耗时 %.0fs  退出码 %d" % (time.time() - t0, p.returncode))
    return p.returncode


def count_lines(path):
    if not os.path.exists(path):
        return 0
    return len([l for l in open(path, encoding="utf-8", errors="replace")
                if l.strip() and "#genre#" not in l])


def verify_mirrors(curated_path, cfg):
    if not os.path.exists(curated_path):
        return
    local = os.path.getsize(curated_path)
    log("")
    log("  镜像核对（本地 %d 字节）：" % local)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for tpl in cfg.get("mirrors", []):
        url = tpl.format(user=cfg.get("user"), repo=cfg.get("repo"),
                         branch=cfg.get("branch", "main"), path="output/curated.txt")
        try:
            r = op.open(urllib.request.Request(url, headers={"User-Agent": "okhttp/3.15"}), timeout=20)
            body = r.read()
            log("    OK   %-16s %d 字节" % ("最新" if len(body) == local else "旧缓存(等5分)", len(body)))
        except Exception as e:  # noqa: BLE001
            log("    ERR  拉取失败 %s" % type(e).__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", default=None, metavar="MEASURED",
                    help="用测速机产出的 measured.txt 换血")
    ap.add_argument("--rebuild", action="store_true", help="全量重建（重抓源池 + 全量测速）")
    ap.add_argument("--from-pool", action="store_true",
                    help="配合 --rebuild：用本地 output/pool.txt 当源池，不联网抓源")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry", action="store_true", help="只预览，不写文件不推送")
    ap.add_argument("--seconds", type=float, default=3.0)
    a = ap.parse_args()

    os.chdir(ROOT)
    logdir = os.path.join(ROOT, "output", "logs")
    os.makedirs(logdir, exist_ok=True)
    logfile = os.path.join(logdir, "run_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
    cfg = {}
    pj = os.path.join(ROOT, "config", "publish.json")
    if os.path.exists(pj):
        cfg = json.load(open(pj, encoding="utf-8"))

    mode = "rebuild" if a.rebuild else ("apply" if a.apply else "check")
    log("iptv 维护  %s  模式=%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), mode))
    log("日志: %s" % logfile)

    curated = os.path.join(ROOT, "output", "curated.txt")
    if not a.rebuild and not a.apply and not os.path.exists(curated):
        log("  找不到 output/curated.txt，改用 --rebuild 全量重建")
        return 2

    # ---------- 全量重建 ----------
    if a.rebuild:
        if a.from_pool:
            step(1, 3, "用本地源池快照全量测速（不联网抓源）")
            src = "output/pool.txt"
            if not os.path.exists(os.path.join(ROOT, src)):
                log("  找不到 %s，改用联网抓源" % src)
                a.from_pool = False
            else:
                cmd = [PY, os.path.join(HERE, "local_speedtest.py"), "--src", src,
                       "--extra", "config/extra_gw_a.txt", "--seconds", str(a.seconds),
                       "--out", "output/measured.txt"]
        if not a.from_pool:
            step(1, 3, "联网抓取源池并全量测速")
            cmd = [PY, os.path.join(HERE, "local_speedtest.py"), "--from-subscribe",
                   "--extra", "config/extra_gw_a.txt", "--seconds", str(a.seconds),
                   "--out", "output/measured.txt"]
        rc = run(cmd, logfile,
                 ("源池合计", "保留", "央视频道", "卫视频道", "xx本地", "ERR"))
        if rc != 0:
            log("  测速失败，旧订阅未改动")
            return rc
        step(2, 3, "合并")
        rc = run([PY, os.path.join(HERE, "merge_tv.py"), "--tv", "output/measured.txt"] + MERGE_ARGS,
                 logfile, ("总条数", "丢弃台", "回补台", "央视频道", "卫视频道", "xx本地"))
        if rc != 0:
            log("  合并失败，旧订阅未改动")
            return rc
        n = count_lines(curated)
        if n < MIN_KEEP:
            log("  !! 仅 %d 条，判定异常，不推送" % n)
            return 3
        # 网关线路按「目标机所在网络」实测优先级重排（编号方案随网关不同，见 reorder_gateways.py）
        log("  按移动网络实测优先级重排网关线路")
        run([PY, os.path.join(HERE, "reorder_gateways.py")], logfile, ("已重排", "无变化"))

    # ---------- 体检（本机测现有线路） ----------
    elif mode == "check":
        step(1, 3, "体检现有订阅（只测 curated.txt 里的线路）")
        rc = run([PY, os.path.join(HERE, "check_speed.py"), "--seconds", str(a.seconds)],
                 logfile, ("可用", "完全失效的台", "进度"))
        if rc != 0:
            log("  体检未产出可用线路，可能是网络/代理问题；旧订阅未改动")
            return rc
        step(2, 3, "换血（失效线路用历史速率表补）")
        cmd = [PY, os.path.join(HERE, "apply_measured.py"), "--min-mbps", "0.1"]
        if a.dry:
            cmd.append("--dry")
        rc = run(cmd, logfile, ("现有", "保留", "[换线]", "[补源]", "[丢弃]", "已写入"))
        if rc != 0:
            log("  换血失败，旧订阅未改动")
            return rc

    # ---------- 用外部结果换血 ----------
    else:
        step(1, 3, "用外部测速结果换血: %s" % a.apply)
        cmd = [PY, os.path.join(HERE, "apply_measured.py"), "--measured", a.apply, "--min-mbps", "0.1"]
        if a.dry:
            cmd.append("--dry")
        rc = run(cmd, logfile, ("现有", "保留", "[换线]", "[补源]", "[丢弃]", "已写入"))
        if rc != 0:
            return rc

    n = count_lines(curated)
    log("")
    log("  当前订阅 %d 条" % n)
    if n < MIN_KEEP:
        log("  !! 条数过少，判定异常，不推送")
        return 3

    # ---------- 推送 ----------
    if a.no_push or a.dry:
        step(3, 3, "推送（已跳过）")
        log("  产物: output/curated.txt")
        return 0
    step(3, 3, "推送到 GitHub")
    rc = run([PY, os.path.join(HERE, "push_file.py")], logfile, ("已推送", "推送失败"))
    if rc != 0:
        log("  推送失败（本地已生成，可稍后重跑 push_file.py）")
        return rc

    verify_mirrors(curated, cfg)
    log("")
    log("完成。播放器里刷新订阅即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
