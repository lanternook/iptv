# -*- coding: utf-8 -*-
"""扫描浙江广电官方 CDN (ali-m-l.cztv.com) 的 channel 编号，找出转播了哪些央视/卫视。

背景：curated 里 CCTV-1=channel16、CCTV-13=channel21，都是这个阿里云 CDN，
属于「官方源」而非家宽网关，晚高峰不受别人家宽上行影响。
若它覆盖全套央视，就是比找网关更稳的方案。

只判活 + 记录分辨率/码率，不做抓帧（抓帧另跑）。
"""
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ssl._create_default_https_context = ssl._create_unverified_context

HOSTS = [
    'http://ali-m-l.cztv.com/channels/lantian/channel%02d/1080p.m3u8',
    'http://ali-m-l.cztv.com/channels/lantian/channel%03d/1080p.m3u8',
]
RANGE = list(range(1, 61))


def get(u, timeout=8):
    h = {'User-Agent': UA, 'Referer': 'https://www.cztv.com/'}
    t0 = time.time()
    try:
        r = op.open(urllib.request.Request(u, headers=h), timeout=timeout)
        return r.status, r.read(4096), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, b'', time.time() - t0
    except Exception as e:  # noqa: BLE001
        return -1, str(e).encode(), time.time() - t0


rows = []
for tpl in HOSTS:
    for n in RANGE:
        u = tpl % n
        c, b, dt = get(u)
        t = b.decode('utf-8', 'replace')
        ok = c == 200 and '#EXTM3U' in t
        if not ok:
            continue
        seg = re.findall(r'^(?!#)(\S+\.ts\S*)$', t, re.M)[:1]
        rows.append({'n': n, 'tpl': tpl, 'url': u, 'code': c,
                     'ms': int(dt * 1000), 'segs': len(seg),
                     'key': bool(re.search(r'#EXT-X-KEY', t)),
                     'head': t[:160]})
        print('  hit channel%-3d %5dms segs=%d' % (n, dt * 1000, len(seg)))

with io.open(os.path.join(TMP, 'cztv_scan.json'), 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

print('命中 %d 个编号: %s' % (len(rows), [r['n'] for r in rows]))
print('-> tmp/cztv_scan.json')
