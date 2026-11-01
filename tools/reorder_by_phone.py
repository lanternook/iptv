# -*- coding: utf-8 -*-
"""按手机（移动网络）3 轮实测重排 curated，并删除完全无源的频道

输入（均由 phone_speed.py 3 轮 + phone_rates_3r.py 产出）：
  tmp/phone_rates_3r.tsv    首选源 3 轮 min
  tmp/cand_rates_3r.tsv     候选源 3 轮 min
  tmp/dead_rates_3r.tsv     待判死源 3 轮 min
  output/curated.txt        当前订阅

输出：
  output/curated.new.txt    新订阅
  tmp/reorder_report.md     变更清单

规则（保守，参照手册 §6）：
  1. 某台全部线路 3 轮 max 均 < 0.1 → 判「无源」，整台删除
  2. 候选源 min ≥ 2.0 且 > 当前首选 min × 1.5 → 提为首选，原首选降为第 2 位
  3. 其余台保持原首选不动，仅把有实测数据的备用按 min 降序
"""
import io, os, sys
from collections import OrderedDict
from urllib.parse import urlsplit

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR = os.path.join(BASE, 'output', 'curated.txt')
NEW = os.path.join(BASE, 'output', 'curated.new.txt')
REP = os.path.join(BASE, 'tmp', 'reorder_report.md')

DEAD_BAR = 0.1     # 判死链
GOOD_BAR = 2.0     # 允许取代首选的最低分
GAIN = 1.5         # 取代首选的最小倍数
TAKEOVER_BAR = 1.0 # 首选已近乎全死时，替补接管所需的最低分


def load_rates(name):
    p = os.path.join(BASE, 'tmp', name)
    d = {}
    if not os.path.exists(p):
        return d
    for line in io.open(p, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        c = line.rstrip('\n').split('\t')
        if len(c) >= 5:
            d[c[0]] = (float(c[1]), float(c[2]), float(c[3]), c[4])
    return d


def load_cand():
    """{(台名, URL): (min, avg, max, flag)}
    列序：频道 min avg max 判定 各轮Mbps URL
    """
    p = os.path.join(BASE, 'tmp', 'cand_rates_3r.tsv')
    d = {}
    if not os.path.exists(p):
        return d
    for line in io.open(p, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        c = line.rstrip('\n').split('\t')
        if len(c) >= 7:
            d[(c[0], c[6])] = (float(c[1]), float(c[2]), float(c[3]), c[4])
    return d


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--drop', default='', help='强制删除的频道，逗号分隔')
    ap.add_argument('--cur', default=CUR, help='输入订阅文件（默认 output/curated.txt）')
    args = ap.parse_args()
    drop = {s.strip() for s in args.drop.split(',') if s.strip()}
    cur_path = args.cur if os.path.isabs(args.cur) else os.path.join(BASE, args.cur)

    prim = load_rates('phone_rates_3r.tsv')
    dead = load_rates('dead_rates_3r.tsv')
    cand = load_cand()

    chans = OrderedDict()
    group = ''
    with io.open(cur_path, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or ',' not in s:
                continue
            name, url = s.split(',', 1)
            if url == '#genre#':
                group = name
                chans.setdefault(('__group__', name), {'g': name, 'u': []})
                continue
            chans.setdefault(name, {'g': group, 'u': []})['u'].append(url)

    out = []
    removed, changed = [], []

    for key, info in chans.items():
        if isinstance(key, tuple):          # 分组标记
            out.append('%s,#genre#' % info['g'])
            continue
        name, urls = key, info['u']

        # 判死：显式名单 或 全部线路 3 轮 max 均 < DEAD_BAR
        if name in drop:
            removed.append((name, len(urls), 0.0))
            continue
        allrate = []
        for i, u in enumerate(urls):
            if i == 0:
                r = prim.get(name) or dead.get(name)
            else:
                r = cand.get((name, u))
            if r:
                allrate.append(r)
        if allrate and all(r[2] < DEAD_BAR for r in allrate):
            removed.append((name, len(urls), min(r[2] for r in allrate)))
            continue

        cur = prim.get(name)
        best = None
        for u in urls[1:]:
            r = cand.get((name, u))
            if not r or r[3] == '死':
                continue
            if best is None or r[0] > best[1][0]:
                best = (u, r)
        swap = False
        if cur and best:
            if best[1][0] >= GOOD_BAR and best[1][0] > cur[0] * GAIN:
                swap = True
            elif cur[0] < DEAD_BAR and best[1][0] >= TAKEOVER_BAR:
                swap = True          # 首选近乎全死（3 轮里多轮 0），替补能跑就上
        if swap:
            old_host = urlsplit(urls[0]).netloc
            new_host = urlsplit(best[0]).netloc
            urls = [best[0]] + [u for u in urls if u != best[0]]
            changed.append((name, cur[0], best[1][0], old_host, new_host))

        for u in urls:
            out.append('%s,%s' % (name, u))

    with io.open(NEW, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')

    # 报告
    L = ['# 重排报告（移动网络 3 轮 min）\n']
    L.append('## 删除（全部线路 3 轮均 < %.1f Mbps）\n' % DEAD_BAR)
    if removed:
        L.append('| 频道 | 线路数 | 最差轮 max |')
        L.append('|---|---|---|')
        for n, c, mx in removed:
            L.append('| %s | %d | %.2f |' % (n, c, mx))
    else:
        L.append('无。')
    L.append('\n## 换首选（候选 min ≥ %.1f 且 > 原首选 × %.1f）\n' % (GOOD_BAR, GAIN))
    if changed:
        L.append('| 频道 | 原首选 min | 新首选 min | 原主机 | 新主机 |')
        L.append('|---|---|---|---|---|')
        for n, o, nw, oh, nh in changed:
            L.append('| %s | %.2f | %.2f | `%s` | `%s` |' % (n, o, nw, oh, nh))
    else:
        L.append('无。')
    L.append('\n## 保持不动\n')
    L.append('其余 %d 台原首选仍最优或候选未达门槛。' % (len(prim) - len(changed) - len(removed)))
    with io.open(REP, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L) + '\n')

    print('删除 %d 台：%s' % (len(removed), '、'.join(n for n, _, _ in removed) or '无'))
    print('换首选 %d 台：%s' % (len(changed), '、'.join(n for n, *_ in changed) or '无'))
    print('->', NEW)
    print('->', REP)


if __name__ == '__main__':
    main()
