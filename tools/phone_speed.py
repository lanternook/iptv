#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""phone_speed.py —— 用手机（目标机同网 = xx移动）测速，一条命令跑完。

为什么必须有这个脚本：本机是**xx电信**（出口 xx.xx.xx.xx），
目标电视盒子是**xx移动**（手机 WiFi 出口 xx.xx.xx.xx）。
两边对同一批源的排名经常完全相反 —— 本机测出来的「最快」到盒子上可能是 0。
所以凡是要**排序 / 置首**，必须用手机结果，本机结果只能判活。

原来要手敲 5 步（push 脚本、push 清单、shell 跑、拉结果、汇总），
每步都有编码/换行坑。本脚本把它们封在一起。

用法:
    python tools/phone_speed.py tmp/list.txt                 # 默认 3 轮，每轮采样 4 秒
    python tools/phone_speed.py tmp/list.txt 2               # 2 轮
    python tools/phone_speed.py tmp/list.txt 3 --sec 5       # 每轮采样 5 秒
    python tools/phone_speed.py tmp/list.txt 3 --keep        # 保留手机上的临时文件

输入清单每行 `台名|URL`（**竖线**，写成逗号整批 m3u8fail）。
脚本会自己重写成 LF 再推送 —— 不用管 Windows 的 CRLF 问题。

输出：
  - 屏幕：每条线路的 3 轮 Mbps + min/avg/max + 死/弱/OK 标记
  - 文件：output/phone_result.txt（原始输出，可直接喂 `find_gateway.py --ingest`
          或 `apply_phone_speed.py --result`）

环境要求：
  - adb 在 tools/adb-tools/platform-tools/adb.exe（自动探测，也可 --adb 指定）
  - 手机已 USB 连接并授权调试；WiFi 已连（移动宽带）
  - 手机需有 curl / sed / grep / awk（小米9 MIUI 自带）
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ADB_CANDIDATES = [
    r"tools/adb-tools/platform-tools/adb.exe",
    r"adb.exe",
]
REMOTE_SH = "/data/local/tmp/phone_speed.sh"
REMOTE_LIST = "/data/local/tmp/urls.txt"


def find_adb(explicit=None):
    if explicit:
        return explicit
    for p in ADB_CANDIDATES:
        if os.path.exists(p):
            return p
    return shutil.which("adb") or "adb"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def load_items(path):
    """读清单，返回 [(tag, url)]。同时兼容 `台名|URL` 与 `标签|频道|URL`。"""
    items = []
    for raw in io.open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        parts = s.split("|")
        url = parts[-1].strip()
        tag = "|".join(parts[:-1]).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        items.append((tag, url))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="清单文件（每行 台名|URL）")
    ap.add_argument("rounds", nargs="?", type=int, default=3, help="轮数，默认 3")
    ap.add_argument("--sec", type=int, default=4, help="每轮采样秒数，默认 4")
    ap.add_argument("--serial", default=None, help="多设备时指定 serial")
    ap.add_argument("--adb", default=None, help="adb 路径")
    ap.add_argument("--keep", action="store_true", help="保留手机上的临时文件")
    args = ap.parse_args()

    adb = find_adb(args.adb)
    env = dict(os.environ, MSYS_NO_PATHCONV="1")

    def A(*a, **kw):
        cmd = [adb] + (["-s", args.serial] if args.serial else []) + list(a)
        return subprocess.run(cmd, capture_output=True, env=env, **kw)

    # 0) 设备
    r = A("devices")
    out = r.stdout.decode("utf-8", "ignore")
    if "\tdevice" not in out:
        print("没有可用设备。先确认：USB 已连、已授权调试、adb 路径正确。")
        print("当前 adb: %s" % adb)
        print(out.strip())
        return 1

    items = load_items(args.src)
    if not items:
        print("清单为空或格式不对（需要 `台名|URL`，用竖线分隔）")
        return 1
    print("设备 OK，共 %d 条线路，测 %d 轮，每轮采样 %d 秒" % (len(items), args.rounds, args.sec))

    # 1) 推送脚本
    sh_src = os.path.join(HERE, "phone_speed.sh")
    if not os.path.exists(sh_src):
        print("缺 %s" % sh_src)
        return 1
    A("push", sh_src, REMOTE_SH)

    # 2) 推送清单 —— 强制 LF，这是最容易踩的坑（CRLF 会让 URL 带 \r → 整批 m3u8fail）
    tmp_list = os.path.join(ROOT, "tmp", "_phone_list.txt")
    os.makedirs(os.path.dirname(tmp_list), exist_ok=True)
    with io.open(tmp_list, "w", encoding="utf-8", newline="") as f:
        for tag, url in items:
            f.write("%s|%s\n" % (tag, url))
    A("push", tmp_list, REMOTE_LIST)

    # 3) 跑 N 轮
    rounds_out = []
    for i in range(1, args.rounds + 1):
        print("--- 手机第 %d/%d 轮 ---" % (i, args.rounds), flush=True)
        r = A("shell", "sh %s %s %d" % (REMOTE_SH, REMOTE_LIST, args.sec), timeout=60 * 30)
        txt = r.stdout.decode("utf-8", "ignore").replace("\r", "")
        print(txt.rstrip(), flush=True)
        rounds_out.append(txt)

    # 4) 落盘（第一轮格式，供 --ingest / apply_phone_speed 用）
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    raw_path = os.path.join(ROOT, "output", "phone_result.txt")
    with io.open(raw_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(rounds_out[0] if rounds_out else "")
    print("\n原始结果（第 1 轮）→ %s" % raw_path)

    # 5) 汇总
    agg = {}
    order = []
    for txt in rounds_out:
        for line in txt.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            p = line.split("|")
            if len(p) < 2:
                continue
            tag = p[0]
            try:
                mbps = float(p[1])
            except ValueError:
                mbps = 0.0
            if tag not in agg:
                agg[tag] = []
                order.append(tag)
            agg[tag].append(mbps)

    print("\n=== 汇总（按 min 降序）===")
    rows = []
    for tag in order:
        v = agg[tag]
        rows.append((tag, v, min(v), sum(v) / len(v), max(v)))
    rows.sort(key=lambda r: r[2], reverse=True)
    for tag, v, mn, av, mx in rows:
        if mx < 1.5:
            flag = "死"
        elif mn < 1.5:
            flag = "弱"
        else:
            flag = "OK"
        print("%-12s %-3s min=%6.2f avg=%6.2f max=%6.2f   %s" % (
            tag, flag, mn, av, mx, " ".join("%.2f" % x for x in v)))

    dead = [r[0] for r in rows if r[4] < 1.5]
    weak = [r[0] for r in rows if r[4] >= 1.5 and r[2] < 1.5]
    print("\n死(%d): %s" % (len(dead), ", ".join(dead) if dead else "无"))
    print("弱(%d): %s" % (len(weak), ", ".join(weak) if weak else "无"))
    print("\n下一步：")
    print("  排序卫视  python tools/apply_phone_speed.py --list %s --result %s --section 卫视频道"
          % (os.path.relpath(tmp_list, ROOT), os.path.relpath(raw_path, ROOT)))
    print("  回灌网关  python tools/find_gateway.py --ingest %s" % os.path.relpath(raw_path, ROOT))

    if not args.keep:
        A("shell", "rm -f %s %s" % (REMOTE_SH, REMOTE_LIST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
