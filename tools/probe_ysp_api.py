# -*- coding: utf-8 -*-
"""批量探测央视频直播接口，找出能直接返回 m3u8/流地址的那一个。

思路：央视频网页是 SPA，接口在 pomodoro / sapi 域名下。
逐个试，只记录 HTTP 状态 + body 前 300 字。
"""
import io
import json
import os
import sys
import ssl
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')

UA_PC = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ssl._create_default_https_context = ssl._create_unverified_context

GUID = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'
PID = '600001859'   # CCTV-1 在央视频的 pid（网页 tv/home?pid= 用的这个）

CAND = [
    ('pomodoro_get_live_stream',
     'https://pomodoro.yangshipin.cn/api/play/v1/live/get_live_stream?pid=%s&client=web&guid=%s' % (PID, GUID)),
    ('pomodoro_live_info',
     'https://pomodoro.yangshipin.cn/api/play/v1/live/get_live_info?pid=%s&client=web&guid=%s' % (PID, GUID)),
    ('pomodoro_v2',
     'https://pomodoro.yangshipin.cn/api/play/v2/live/get_live_stream?pid=%s&client=web&guid=%s' % (PID, GUID)),
    ('sapi_live',
     'https://sapi.yangshipin.cn/api/play/v1/live/get_live_stream?pid=%s&client=web&guid=%s' % (PID, GUID)),
    ('ysp_vdn_live',
     'https://vdn.live.cntv.cn/api2/liveHtml5.do?pid=%s&client=web&guid=%s' % (PID, GUID)),
    ('cntv_vdn_live',
     'https://vdn.live.cntv.cn/api2/liveHtml5.do?pid=%s' % PID),
    ('cntv_api_v3',
     'https://vdn.apps.cntv.cn/api/v3/vdn/live?pid=%s' % PID),
    ('ysp_h5_player',
     'https://m.yangshipin.cn/static/project/test/player/vr/index.js'),
]


def hit(name, url):
    h = {'User-Agent': UA_PC, 'Referer': 'https://www.yangshipin.cn/',
         'Accept': 'application/json,text/plain,*/*',
         'Origin': 'https://www.yangshipin.cn'}
    t0 = time.time()
    try:
        r = op.open(urllib.request.Request(url, headers=h), timeout=15)
        b = r.read()
        return {'name': name, 'url': url, 'code': r.status, 'ms': int((time.time() - t0) * 1000),
                'bytes': len(b), 'body': b.decode('utf-8', 'replace')[:300]}
    except urllib.error.HTTPError as e:
        b = e.read()
        return {'name': name, 'url': url, 'code': e.code, 'ms': int((time.time() - t0) * 1000),
                'bytes': len(b), 'body': b.decode('utf-8', 'replace')[:300]}
    except Exception as e:  # noqa: BLE001
        return {'name': name, 'url': url, 'code': -1, 'ms': int((time.time() - t0) * 1000),
                'bytes': 0, 'body': str(e)[:200]}


rows = [hit(n, u) for n, u in CAND]
with io.open(os.path.join(TMP, 'ysp_api_probe.json'), 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

for r in rows:
    print('%-26s %4s %5dms %6dB  %s' % (r['name'], r['code'], r['ms'], r['bytes'],
                                        r['body'][:110].replace('\n', ' ')))
print('-> tmp/ysp_api_probe.json')
