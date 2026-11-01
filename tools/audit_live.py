#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""订阅全量「活性审计」：识别冻结快照 / 死链。

背景：上一轮用「能不能拉到分片」判活，结果把 CDN 上的历史快照当成活源。
快照的分片仍在 CDN 上、拉得飞快，测速排名第一，但播放器卡在第一帧。
判据必须换成「播放列表是否滚动」。

指纹 = (MEDIA-SEQUENCE, 最后一个分片 URI)
两次取样（间隔 N 秒）指纹变化 => 滚动 => 真直播。

用法：
  python tools/audit_live.py output/curated.txt --wait 14 --workers 24
输出 tmp/audit_live.json + 屏幕分类汇总
"""
import argparse
import json
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = 'okhttp/3.12.0'
LOCK = threading.Lock()


def fetch_pl(url, timeout=10):
    """取播放列表，返回 (指纹, 状态)。"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        r = OP.open(req, timeout=timeout)
        body = r.read(60000).decode('utf-8', 'replace')
        code = r.getcode()
    except Exception as e:
        return None, 'ERR:' + str(e)[:50]

    if code != 200:
        return None, 'HTTP%d' % code
    if '#EXTM3U' not in body:
        return None, 'NOT_M3U8'

    m = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', body)
    seq = m.group(1) if m else ''
    segs = [ln.strip() for ln in body.splitlines()
            if ln.strip() and not ln.startswith('#')]
    if not segs:
        return None, 'NO_SEG'
    return (seq, segs[-1]), 'OK'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?', default='output/curated.txt')
    ap.add_argument('--wait', type=int, default=14)
    ap.add_argument('--workers', type=int, default=24)
    ap.add_argument('--out', default='tmp/audit_live.json')
    a = ap.parse_args()

    lines = []
    with open(a.path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ',' not in ln or ln.endswith('#genre#'):
                continue
            name, url = ln.split(',', 1)
            lines.append({'name': name.strip(), 'url': url.strip()})
    print('共 %d 条线路，第一轮取样...' % len(lines))

    def probe(rec):
        fp, st = fetch_pl(rec['url'])
        rec['fp1'], rec['st1'] = fp, st
        return rec

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        lines = list(ex.map(probe, lines))

    ok1 = sum(1 for r in lines if r['fp1'])
    print('第一轮可用 %d / %d，等 %d 秒做滚动判定...'
          % (ok1, len(lines), a.wait))
    time.sleep(a.wait)

    def probe2(rec):
        if not rec['fp1']:
            rec['verdict'] = 'dead'
            return rec
        fp2, st2 = fetch_pl(rec['url'])
        rec['fp2'], rec['st2'] = fp2, st2
        if not fp2:
            rec['verdict'] = 'dead'
        elif fp2 != rec['fp1']:
            rec['verdict'] = 'live'
        else:
            rec['verdict'] = 'frozen'
        return rec

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        lines = list(ex.map(probe2, lines))

    live = [r for r in lines if r['verdict'] == 'live']
    frozen = [r for r in lines if r['verdict'] == 'frozen']
    dead = [r for r in lines if r['verdict'] == 'dead']

    print('\n=== 汇总 ===')
    print('真直播 %d 条 / 冻结快照 %d 条 / 死链 %d 条'
          % (len(live), len(frozen), len(dead)))

    if frozen:
        print('\n--- 冻结快照（必须剔除，播放会卡第一帧）---')
        for r in frozen:
            print('  %-12s %s' % (r['name'], r['url'][:78]))
    if dead:
        print('\n--- 死链 ---')
        for r in dead:
            print('  %-12s %-10s %s'
                  % (r['name'], r['st1'], r['url'][:70]))

    # 按台统计存活线路数
    from collections import defaultdict
    stat = defaultdict(lambda: {'live': 0, 'frozen': 0, 'dead': 0})
    for r in lines:
        stat[r['name']][r['verdict']] += 1
    print('\n--- 每台存活线路 ---')
    for name in sorted(stat):
        s = stat[name]
        flag = '  !! 无活线' if s['live'] == 0 else ''
        print('  %-12s live=%d frozen=%d dead=%d%s'
              % (name, s['live'], s['frozen'], s['dead'], flag))

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(lines, f, ensure_ascii=False, indent=1)
    print('\n-> ' + a.out)


if __name__ == '__main__':
    main()
