#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speed_multi.py —— 多条线路 N 轮测速，按台名或按 URL 聚合，输出 min/avg/max。

为什么需要它：单次测速会把「假快」源选进来（首测 16 Mbps，紧接三轮全挂）。
判据要用 **min（N 轮最低值）**，晚高峰看的就是最差那一轮。

测速引擎复用 local_speedtest.measure()（解析 .m3u8 到 .ts 分片计时）。
注意：不要自己用 `ffmpeg -loglevel error` 解析 bitrate —— error 级别不输出统计，
自解析会全部得 0.0，看起来像「全线已死」。

用法:
    python tools/speed_multi.py 清单.txt                  # 默认 3 轮，按台名聚合
    python tools/speed_multi.py 清单.txt 5                # 5 轮
    python tools/speed_multi.py 清单.txt 3 --by-url       # 按 URL 逐条聚合（推荐）
    python tools/speed_multi.py 清单.txt 3 --seconds 4 --workers 4

清单格式（每行一条，脚本按**最后一个** `|` 切分）:
    台名|URL
    标签|频道|URL

输入文件必须是 UTF-8 + LF。若清单是给手机 phone_speed.sh 用的，
Windows 下写文件务必 `open(..., 'w', encoding='utf-8', newline='')`，
否则 CRLF 会让 URL 尾部带 `\\r`，整批 m3u8fail。
"""
import argparse
import concurrent.futures as cf
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import local_speedtest as L  # noqa: E402


def load_items(path):
    items = []
    for i, raw in enumerate(io.open(path, encoding="utf-8")):
        s = raw.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        parts = s.split("|")
        url = parts[-1].strip()
        tag = "|".join(parts[:-1]).strip()
        if not url.lower().startswith(("http://", "https://", "rtmp://", "rtsp://")):
            continue
        items.append((i, tag, url))
    return items


def run(items, rounds, seconds, workers):
    """返回 {key: [tag, url, [mbps...]]}"""
    res = {}
    for r in range(1, rounds + 1):
        print("--- 第 %d/%d 轮 ---" % (r, rounds), flush=True)
        with cf.ThreadPoolExecutor(workers) as ex:
            out = list(ex.map(
                lambda it: L.measure((it[1], it[2]), seconds, 2_000_000), items))
        for (i, tag, url), (name, u, mbps, note) in zip(items, out):
            res.setdefault(i, [tag, url, []])[2].append(mbps)
    return res


def flag_of(vals):
    mx, mn = max(vals), min(vals)
    if mx < 1.5:
        return "死"
    if mn < 1.5:
        return "弱"
    return "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="清单文件")
    ap.add_argument("rounds", nargs="?", type=int, default=3, help="轮数，默认 3")
    ap.add_argument("--by-url", action="store_true",
                    help="按 URL 逐条聚合（默认按台名聚合）")
    ap.add_argument("--seconds", type=float, default=3.0, help="每轮采样秒数，默认 3")
    ap.add_argument("--workers", type=int, default=5, help="并发，默认 5")
    args = ap.parse_args()

    items = load_items(args.src)
    if not items:
        print("清单为空或格式不对（需要 `台名|URL`）")
        return 1
    print("共 %d 条，测 %d 轮，每轮采样 %.0f 秒" % (len(items), args.rounds, args.seconds))

    res = run(items, args.rounds, args.seconds, args.workers)

    if args.by_url:
        rows = [(res[i][0], res[i][1], res[i][2]) for i in sorted(res)]
    else:
        agg = {}
        order = []
        for i in sorted(res):
            tag, url, v = res[i]
            if tag not in agg:
                agg[tag] = []
                order.append(tag)
            agg[tag].extend(v)
        rows = [(t, "", agg[t]) for t in order]

    print("\n=== 汇总（按 min 降序）===")
    rows.sort(key=lambda r: min(r[2]), reverse=True)
    for tag, url, v in rows:
        mn, mx = min(v), max(v)
        av = sum(v) / len(v)
        line = "%-10s %-3s min=%5.2f avg=%5.2f max=%5.2f" % (
            tag, flag_of(v), mn, av, mx)
        if url:
            line += "  " + url[:72]
        print(line)

    dead = [r[0] for r in rows if flag_of(r[2]) == "死"]
    weak = [r[0] for r in rows if flag_of(r[2]) == "弱"]
    print("\n死(%d): %s" % (len(dead), ", ".join(dead) if dead else "无"))
    print("弱(%d): %s" % (len(weak), ", ".join(weak) if weak else "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
