# -*- coding: utf-8 -*-
"""按编号整段枚举 txiptv 类直链主机，补齐央视缺的台。

背景：`/tsfile/live/00NN_1.m3u8?key=txiptv&playlive=1&authid=0` 这类地址的
编号是**供应商统一编号**，不是单机私有编号——已在 3 台主机上交叉验证：

    0001~0015 -> CCTV-1~15
    0016      -> CCTV-17（这些源都没有 CCTV-16，编号顺移，和网关一个毛病）

所以不用逐个抓帧猜编号，直接整段枚举，缺哪个补哪个。

用法：
    python tools/fill_tsfile.py                 # 生成候选清单 tmp/ts_cand.txt
    python tools/fill_tsfile.py --hosts-only    # 只打印主机表，不生成
    python tools/fill_tsfile.py --max 200       # 限制候选条数
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(ROOT, "output", "pool.txt")
CURATED = os.path.join(ROOT, "output", "curated.txt")
OUT = os.path.join(ROOT, "tmp", "ts_cand.txt")

SUFFIX = "?key=txiptv&playlive=1&authid=0"
PATH = "/tsfile/live/%04d_1.m3u8"

# 编号 -> 台名。0016 是 CCTV-17，不是 CCTV-16。
NUM2TAG = {}
for n in range(1, 16):
    NUM2TAG[n] = "CCTV-%d" % n
NUM2TAG[16] = "CCTV-17"


def log(msg=""):
    print(msg)


def read_pairs(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for ln in io.open(path, encoding="utf-8", errors="ignore"):
        ln = ln.strip()
        if not ln or ln.startswith("#") or "," not in ln:
            continue
        tag, url = ln.split(",", 1)
        rows.append((tag.strip(), url.strip()))
    return rows


def collect_hosts(pool_rows, cur_rows):
    """找出所有 txiptv 主机。清单里在用的优先（已证明可用）。"""
    known = []   # 清单里已有 00NN 的
    extra = []   # 池里出现过 00NN 的
    for tag, url in cur_rows:
        m = re.match(r"https?://([^/]+)/tsfile/live/(00\d{2})_1\.m3u8", url)
        if m and m.group(1) not in known:
            known.append(m.group(1))
    for tag, url in pool_rows:
        m = re.match(r"https?://([^/]+)/tsfile/live/(00\d{2})_1\.m3u8", url)
        if m and m.group(1) not in known and m.group(1) not in extra:
            extra.append(m.group(1))
    return known, extra


def main():
    hosts_only = "--hosts-only" in sys.argv
    maxn = 200
    for i, a in enumerate(sys.argv):
        if a == "--max" and i + 1 < len(sys.argv):
            maxn = int(sys.argv[i + 1])

    pool_rows = read_pairs(POOL)
    cur_rows = read_pairs(CURATED)
    log("池 %d 条 / 清单 %d 条" % (len(pool_rows), len(cur_rows)))

    known, extra = collect_hosts(pool_rows, cur_rows)
    log("txiptv 主机：清单在用的 %d 个，池里新发现的 %d 个" % (len(known), len(extra)))
    for h in known:
        log("  [在用] %s" % h)
    for h in extra:
        log("  [新]   %s" % h)
    if hosts_only:
        return 0

    # 清单里已有的 URL，避免重复送测
    have = set()
    for tag, url in cur_rows:
        have.add(url)

    rows = []
    skipped = 0
    for h in known + extra:
        scheme = "https" if h.endswith(":443") else "http"
        for n in sorted(NUM2TAG):
            url = "%s://%s%s%s" % (scheme, h, PATH % n, SUFFIX)
            if url in have:
                skipped += 1
                continue
            rows.append((NUM2TAG[n], url))

    if len(rows) > maxn:
        log("候选 %d 条，按 --max 截到 %d 条" % (len(rows), maxn))
        rows = rows[:maxn]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # 注意：phone_speed.sh 的输入是「标签|URL」，不是逗号，写错会整批 m3u8fail
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for tag, url in rows:
            f.write("%s|%s\n" % (tag, url))

    # 按台统计缺口
    per = {}
    for tag, url in rows:
        per[tag] = per.get(tag, 0) + 1
    log("")
    log("生成 %d 条候选（清单已存在跳过 %d 条）-> %s" % (len(rows), skipped, OUT))
    miss = [t for t in sorted(per, key=lambda x: (len(x), x)) if per[t]]
    log("覆盖 %d 个台：%s" % (len(miss), "  ".join("%s×%d" % (t, per[t]) for t in miss)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
