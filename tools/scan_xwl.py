#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描浙江广电真直播 CDN：ali-xwl.cztv.com/live/channelNN{1080P|720P}lxw.m3u8

已知 channel01 = 浙江卫视（滚动验证通过）。
本脚本对 1~40 编号 × 两档码率全部探测，并做「两次取样比 seq」滚动判定。
输出 tmp/xwl_scan.json
"""
import json
import re
import time
import urllib.request

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = 'okhttp/3.12.0'
TMPL = 'http://ali-xwl.cztv.com/live/channel%02d%sPlxw.m3u8'
RATES = ['1080', '720']
NUMS = list(range(1, 41))


def get(u, timeout=8):
    r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA}),
                timeout=timeout)
    return r.getcode(), r.read(20000).decode('utf-8', 'replace')


def seq_of(t):
    m = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', t)
    return int(m.group(1)) if m else None


def main():
    # 第一轮：判 200 + 有 seq
    hits = []
    for n in NUMS:
        for rt in RATES:
            u = TMPL % (n, rt)
            try:
                c, t = get(u)
                s = seq_of(t)
                if c == 200 and s is not None:
                    hits.append({'n': n, 'rate': rt, 'url': u, 'seq1': s})
                    print('  命中 %-3d %-5s seq=%s' % (n, rt, s))
            except Exception as e:
                msg = str(e)[:40]
                if '404' not in msg:
                    print('  异常 %-3d %-5s %s' % (n, rt, msg))
    print('第一轮命中 %d 条' % len(hits))

    # 第二轮：滚动判定
    print('\n等 12 秒做滚动判定...')
    time.sleep(12)
    for h in hits:
        try:
            c, t = get(h['url'])
            s2 = seq_of(t)
            h['seq2'] = s2
            h['live'] = (s2 is not None and s2 > h['seq1'])
        except Exception as e:
            h['seq2'] = None
            h['live'] = False
            h['err'] = str(e)[:50]
        print('  %-3d %-5s seq %s->%s %s'
              % (h['n'], h['rate'], h['seq1'], h.get('seq2'),
                 'LIVE' if h.get('live') else 'frozen'))

    with open('tmp/xwl_scan.json', 'w', encoding='utf-8') as f:
        json.dump(hits, f, ensure_ascii=False, indent=1)
    live = [h['n'] for h in hits if h.get('live')]
    print('\n真直播编号: %s' % sorted(set(live)))
    print('-> tmp/xwl_scan.json')


if __name__ == '__main__':
    main()
