#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""promote_cdn.py —— 把实测最快的公网 CDN 直链提到该台第一条（网关退为备用）。

背景：IPTV 转发网关晚高峰会整体瘫（实测 0.1~1.5 Mbps），而公网 CDN 直链同一时段
仍有 10~40 Mbps。所以晚高峰时应该让 CDN 直链打头，网关当兜底。

输入：
  --list    送测清单，每行 `CCTV-x|url`
  --result  手机返回，每行 `CCTV-x|Mbps|code|bytes`
  --min-mbps 达到这个速率的直链才会被提到首位（默认 4.0）
输出：原地改 curated.txt 的央视频道分组
  - 每台取「可用且 >= min-mbps」里最快的一条，移到该台第一行
  - 已经是第一条则不动（幂等）
  - 低于阈值的台完全不动（保持原有网关首选）

用法:
  python tools/promote_cdn.py --list tmp/cdn_cand.txt --result tmp/cdn_res.txt
  python tools/promote_cdn.py ... --min-mbps 8 --dry
"""
import argparse
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CCTV_RE = re.compile(r"^CCTV[-_ ]?(\d{1,2})(\+)?$", re.I)


def norm(name):
    """把 CCTV13 / CCTV-13 / cctv_5+ 统一成 CCTV-13 / CCTV-5+；不规范返回 None。"""
    m = CCTV_RE.match(name.strip())
    if not m:
        return None
    return "CCTV-%d%s" % (int(m.group(1)), "+" if m.group(2) else "")


def load_list(path):
    """返回 [(tag, url)]，保持行序（送测清单里同名台会出现多次，不能用 dict）。"""
    out = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if not s or "|" not in s:
            continue
        tag, url = s.split("|", 1)
        out.append((tag.strip(), url.strip()))
    return out


def load_result(path):
    """返回 [(tag, mbps_or_0)]，与清单逐行对应。"""
    out = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        p = raw.strip().split("|")
        if len(p) < 4:
            continue
        try:
            mbps = float(p[1])
            nbytes = int(float(p[3]))
        except ValueError:
            mbps, nbytes = 0.0, 0
        ok = p[2] == "200" and nbytes >= 100000
        out.append((p[0].strip(), mbps if ok else 0.0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--section", default="央视频道")
    ap.add_argument("--min-mbps", type=float, default=4.0)
    ap.add_argument("--inp", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    pairs = load_list(a.list)
    res = load_result(a.result)
    if len(pairs) != len(res):
        print("清单 %d 行 / 结果 %d 行 不一致，拒绝处理" % (len(pairs), len(res)))
        return 1

    # 每台挑最快的一条（逐行配对）
    best = {}
    for (tag, url), (rtag, mbps) in zip(pairs, res):
        if mbps < a.min_mbps:
            continue
        name = norm(tag.split("#")[0])
        if not name:
            continue
        if name not in best or mbps > best[name][1]:
            best[name] = (url, mbps)

    old = open(a.inp, encoding="utf-8").read()
    lines = old.splitlines()
    out, section = [], None
    cur, items = None, []
    promoted = []

    def flush():
        nonlocal cur, items
        if cur is None:
            return
        target = best.get(cur)
        if target:
            url, mbps = target
            if items and items[0] == url:
                promoted.append((cur, mbps, "已是首选"))
            else:
                items = [url] + [u for u in items if u != url]
                promoted.append((cur, mbps, "提到首位"))
        out.extend("%s,%s" % (cur, u) for u in items)
        cur, items = None, []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.endswith(",#genre#"):
            flush()
            section = s.split(",")[0]
            out.append(s)
            continue
        if "," not in s:
            flush()
            out.append(s)
            continue
        name, url = s.split(",", 1)
        if section == a.section:
            if name != cur:
                flush()
                cur = name
            items.append(url)
        else:
            out.append(s)
    flush()

    new = "\n".join(out) + "\n"
    for name, mbps, act in promoted:
        print("  %-10s %6.2f Mbps  %s" % (name, mbps, act))
    print("达标台 %d 个（阈值 %.1f Mbps）" % (len(best), a.min_mbps))
    if new == old:
        print("无变化")
        return
    if a.dry:
        print("（dry）未写入")
        return
    shutil.copyfile(a.inp, a.inp + ".bak")
    open(a.inp, "w", encoding="utf-8", newline="\n").write(new)
    print("已写入 %s（%d -> %d 行）" % (a.inp, len(lines), len(new.splitlines())))


if __name__ == "__main__":
    main()
