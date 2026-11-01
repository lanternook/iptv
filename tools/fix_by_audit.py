#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「活性审计」结果修正订阅：剔除冻结快照、降权已死主机。

两类问题：
  1. 冻结快照 —— CDN 上的历史对象，分片能拉、速度极快，但列表不滚动，
     播放器卡在第一帧。必须删，且不会自愈。
  2. 主机整体不可达 —— 单次超时不足以判死（可能临时限流），
     只降权到该台末位，保留观察。

用法：
  python tools/fix_by_audit.py output/curated.txt tmp/audit_live.json [--apply]
不加 --apply 只打印改动，不写盘。
"""
import argparse
import json
import re
import shutil
from collections import defaultdict


def host_of(u):
    m = re.match(r'https?://([^/:]+)(?::(\d+))?', u)
    if not m:
        return u
    return m.group(1) + (':' + m.group(2) if m.group(2) else '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', default='output/curated.txt', nargs='?')
    ap.add_argument('audit', default='tmp/audit_live.json', nargs='?')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    audit = json.load(open(a.audit, encoding='utf-8'))
    frozen_urls = {r['url'] for r in audit if r['verdict'] == 'frozen'}

    # 注意：本机不可达**不能**作为降权依据。
    # 本机出口是xx电信，目标盒子是xx移动，两边路由常相反。
    # 实测 119.125.131.239（移动 IP）本机全超时，手机上 7~29 Mbps 全 OK。
    # 所以这里只处理「冻结快照」——那是 CDN 内容属性，与网络无关，任何网络都放不出来。
    dead_hosts = set()

    print('冻结快照 %d 条（将删除）' % len(frozen_urls))

    # 读原文，保持 genre 分组结构
    raw = open(a.path, encoding='utf-8').read().splitlines()
    groups = []          # [(genre 行 或 None, [(name,url)...])]
    cur = None
    for ln in raw:
        s = ln.strip()
        if not s:
            continue
        if s.endswith('#genre#'):
            cur = (s, [])
            groups.append(cur)
        else:
            if ',' not in s:
                continue
            n, u = s.split(',', 1)
            if cur is None:
                cur = (None, [])
                groups.append(cur)
            cur[1].append((n.strip(), u.strip()))

    removed, moved = [], []
    out_groups = []
    for genre, items in groups:
        # 按台聚合，保持台的原始出现顺序
        order, bucket = [], defaultdict(list)
        for n, u in items:
            if n not in bucket:
                order.append(n)
            bucket[n].append(u)

        new_items = []
        for n in order:
            urls = []
            for u in bucket[n]:
                if u in frozen_urls:
                    removed.append((n, u))
                    continue
                urls.append(u)
            # 整机不可达的线路降到末位（保留观察）
            ok = [u for u in urls if host_of(u) not in dead_hosts]
            bad = [u for u in urls if host_of(u) in dead_hosts]
            for u in bad:
                moved.append((n, u))
            new_items.extend((n, u) for u in ok + bad)

        if new_items:
            out_groups.append((genre, new_items))

    print('\n--- 删除冻结快照 %d 条 ---' % len(removed))
    for n, u in removed:
        print('  %-12s %s' % (n, u[:76]))
    print('\n--- 降权到末位 %d 条（整机不可达）---' % len(moved))
    for n, u in moved:
        print('  %-12s %s' % (n, u[:76]))

    lines = []
    for genre, items in out_groups:
        if genre:
            lines.append(genre)
        for n, u in items:
            lines.append('%s,%s' % (n, u))

    total = sum(1 for ln in lines if not ln.endswith('#genre#'))
    print('\n原 %d 条 -> 新 %d 条' % (len(raw) - len(raw) + sum(
        1 for ln in raw if ln.strip() and not ln.strip().endswith('#genre#')),
        total))

    if a.apply:
        shutil.copy(a.path, a.path + '.bak.audit')
        with open(a.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        print('\n已写入 %s（备份 %s.bak.audit）' % (a.path, a.path))
    else:
        print('\n[试运行] 未写盘，加 --apply 生效')


if __name__ == '__main__':
    main()
