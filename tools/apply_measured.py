#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_measured.py —— 用测速机的体检结果换血，其余保持现有成果不变。

只做一件事：把 curated.txt 里已失效的线路换掉。
  · 仍可用的线路：原样保留（顺序、网关置首、分组都不动）
  · 失效的线路：从 rates.tsv 里该台的达标线路补（按速率降序）
  · 补不到的台：整台移除，并在变更清单里列出

用法:
    python tools/apply_measured.py                      # 用 output/measured.txt 换血
    python tools/apply_measured.py --measured D:/measured.txt --dry   # 只预览不写
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def parse(path):
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


def load_rates(path):
    """返回 {台名: [(mbps, url), ...]}，按速率降序。"""
    by_name = {}
    if not os.path.exists(path):
        return by_name
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3:
            try:
                m = float(p[1])
            except ValueError:
                continue
            by_name.setdefault(p[0].strip(), []).append((m, p[2].strip()))
    for k in by_name:
        by_name[k].sort(reverse=True)
    return by_name


def load_banned():
    p = os.path.join(ROOT, "config", "url_blacklist.txt")
    out = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--measured", default=os.path.join(ROOT, "output", "measured.txt"))
    ap.add_argument("--rates", default=os.path.join(ROOT, "output", "rates.tsv"))
    ap.add_argument("--out", default=None, help="默认原地覆盖 --curated")
    ap.add_argument("--min-mbps", type=float, default=0.1, help="补源时的存活线（0.1 = 只要能拉到数据）")
    ap.add_argument("--per-channel", type=int, default=3, help="每台最多保留几条")
    ap.add_argument("--dry", action="store_true", help="只打印变更，不写文件")
    a = ap.parse_args()

    if not os.path.exists(a.curated):
        sys.exit("找不到现有订阅: %s" % a.curated)
    if not os.path.exists(a.measured):
        sys.exit("找不到测速结果: %s（先在测速机上跑 check_speed.py）" % a.measured)

    base = parse(a.curated)
    alive = {(n, u) for _g, items in parse(a.measured) for n, u in items}
    rates = load_rates(a.rates)
    banned = load_banned()

    lines, changes = [], []
    kept_n = swap_n = drop_n = 0
    for gname, items in base:
        out = []
        for n in dict.fromkeys(x[0] for x in items):          # 保持原台顺序、去重
            urls = [u for x, u in items if x == n]
            good = [u for u in urls if (n, u) in alive]
            if good:
                kept_n += 1
                out.extend((n, u) for u in good[: a.per_channel])
                dropped = len(urls) - len(good)
                if dropped:
                    changes.append("[换线] %s：%d 条失效已移除" % (n, dropped))
                continue
            # 全部失效：从历史速率表补
            alts = [u for m, u in rates.get(n, [])
                    if m >= a.min_mbps and not any(k in u for k in banned) and u not in urls]
            if alts:
                swap_n += 1
                out.extend((n, u) for u in alts[: a.per_channel])
                changes.append("[补源] %s：%d 条旧线路失效，补入 %d 条历史达标线路"
                               % (n, len(urls), min(len(alts), a.per_channel)))
            else:
                drop_n += 1
                changes.append("[丢弃] %s：%d 条全部失效且无备用源" % (n, len(urls)))
        if out:
            lines.append("%s,#genre#" % gname)
            lines.extend("%s,%s" % (n, u) for n, u in out)

    text = "\n".join(lines) + "\n"
    n_base_ch = len(dict.fromkeys(n for _g, it in base for n, _u in it))
    n_base = sum(len(it) for _g, it in base)
    n_out = sum(1 for l in lines if "#genre#" not in l)
    print("现有 %d 台 / %d 条 → 换血后 %d 条" % (n_base_ch, n_base, n_out))
    print("保留 %d 台 / 补源 %d 台 / 丢弃 %d 台" % (kept_n, swap_n, drop_n))
    for c in changes:
        print("  " + c)

    if a.dry:
        print("\n--dry：未写文件")
        return 0
    dest = a.out or a.curated
    open(dest, "w", encoding="utf-8").write(text)
    print("\n已写入 %s" % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
