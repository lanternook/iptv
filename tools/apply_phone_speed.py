#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_phone_speed.py —— 用手机（目标机同网）测速结果给指定分组的线路排序。

输入：
  --list    送测清单，每行 `台名#NN|url`
  --result  手机返回，每行 `台名#NN|Mbps|httpcode|bytes`
输出：原地重写 curated.txt 指定分组的线路顺序
  - 排序键：可用(200) 优先 → Mbps 降序 → 原始顺序
  - 死链（非 200 / m3u8fail / 0 字节）沉到该台末尾，**不删除**
  - 分组内台的先后顺序保持原样

用法:
  python tools/apply_phone_speed.py --list tmp_ws.txt --result tmp_ws_res.txt --section 卫视频道
  python tools/apply_phone_speed.py --list ... --result ... --section 卫视频道 --dry
"""
import argparse
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_list(path):
    """name#NN|url -> {tag: url}，tag 就是 '台名#NN'"""
    d = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if not s or "|" not in s:
            continue
        tag, url = s.split("|", 1)
        d[tag.strip()] = url.strip()
    return d


def load_result(path):
    """tag|mbps|code|bytes -> {tag: (alive, mbps)}"""
    d = {}
    for raw in open(path, encoding="utf-8", errors="replace"):
        s = raw.strip()
        if not s or "|" not in s:
            continue
        p = s.split("|")
        if len(p) < 3:
            continue
        tag = p[0].strip()
        try:
            mbps = float(p[1])
        except ValueError:
            mbps = 0.0
        code = p[2].strip()
        tail = p[3].strip() if len(p) > 3 else ""
        try:
            nbytes = int(float(tail)) if tail and tail != "m3u8fail" else 0
        except ValueError:
            nbytes = 0
        # 200 但只回了 334 字节这种空壳也算死链
        alive = code == "200" and mbps > 0 and nbytes >= 100000
        d[tag] = (alive, mbps)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--section", default="卫视频道")
    ap.add_argument("--inp", default=os.path.join(ROOT, "output", "curated.txt"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    tag_url = load_list(a.list)
    stat = load_result(a.result)

    old = open(a.inp, encoding="utf-8").read()
    lines = old.splitlines()

    # 按 tag 反查每个 URL 的测速结果
    def key_of(url):
        for tag, u in tag_url.items():
            if u == url:
                return tag
        return None

    out, section = [], None
    blocks = []          # [(台名, [url,...])] 当前分组的台块
    cur = None

    def flush_block():
        nonlocal cur
        if cur is None:
            return
        name, urls = cur
        scored = []
        for i, u in enumerate(urls):
            tag = key_of(u)
            alive, mbps = stat.get(tag, (False, 0.0)) if tag else (False, 0.0)
            scored.append((0 if alive else 1, -mbps, i, u, mbps, alive))
        scored.sort()
        blocks.append((name, [x[3] for x in scored], scored))
        cur = None

    def flush_section():
        for name, urls, scored in blocks:
            out.extend("%s,%s" % (name, u) for u in urls)
            dead = [x for x in scored if not x[5]]
            if dead:
                print("  [死链] %s：%d 条（已沉底，未删除）" % (name, len(dead)))
        blocks.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.endswith(",#genre#"):
            flush_block()
            if section == a.section:
                flush_section()
            section = s.split(",")[0]
            out.append(s)
            continue
        if "," not in s:
            flush_block()
            out.append(s)
            continue
        name, url = s.split(",", 1)
        if section == a.section:
            if cur is None or cur[0] != name:
                flush_block()
                cur = (name, [])
            cur[1].append(url)
        else:
            out.append(s)
    flush_block()
    if section == a.section:
        flush_section()

    new = "\n".join(out) + "\n"
    if new == old:
        print("无变化")
        return
    if a.dry:
        print("（dry）将重写 %s 的 %d 个台块" % (a.section, len(blocks) or 0))
        return
    shutil.copyfile(a.inp, a.inp + ".bak")
    open(a.inp, "w", encoding="utf-8", newline="\n").write(new)
    print("已按测速结果重排 %s：%d 行 -> %d 行"
          % (a.section, len(old.splitlines()), len(new.splitlines())))


if __name__ == "__main__":
    main()
