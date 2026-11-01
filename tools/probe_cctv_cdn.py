# -*- coding: utf-8 -*-
"""验证央视网 CDN 直链：no-DRM(nd) 与 DRM(cdrm) 两套前缀的实际可用性。

liveplayer.js 里硬编码的模板：
  http://ldncctvwb{nd|cd}{cdn}.{host}/ldncctvwb{nd|cd}/ldcctv{N}_2/index.m3u8
  - nd   = 无 DRM
  - cdrm = CCTV DRM（cdrmldcctv1_1）

逐条拉 m3u8 看是否 #EXTM3U、有无 EXT-X-KEY、分片类型。
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
os.makedirs(TMP, exist_ok=True)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ssl._create_default_https_context = ssl._create_unverified_context

CDN = {
    'ali': 'ldncctvwb%sali.v.myalicdn.com',
    'bd': 'ldncctvwb%sbd.a.bdydns.com',
    'cnc': 'ldncctvwb%scnc.v.wscdns.com',
    'hwy': 'ldncctvwb%shwy.cntv.myhwcdn.cn',
    'ks': 'ldncctvwb%sks.v.kcdnvip.com',
    'txy': 'ldncctvwb%stxy.liveplay.myqcloud.com',
}


def get(u, timeout=12, referer='https://tv.cctv.com/'):
    h = {'User-Agent': UA, 'Referer': referer, 'Accept': '*/*'}
    t0 = time.time()
    try:
        r = op.open(urllib.request.Request(u, headers=h), timeout=timeout)
        b = r.read()
        return r.status, b, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, b'', time.time() - t0
    except Exception as e:  # noqa: BLE001
        return -1, str(e).encode(), time.time() - t0


def inspect(u):
    code, b, dt = get(u)
    t = b.decode('utf-8', 'replace')
    d = {'url': u, 'code': code, 'bytes': len(b), 'ms': int(dt * 1000),
         'm3u8': '#EXTM3U' in t}
    d['key'] = re.findall(r'#EXT-X-KEY:([^\n]+)', t)[:2]
    d['variant'] = re.findall(r'^(?!#)(\S+\.m3u8.*)$', t, re.M)[:2]
    d['seg'] = re.findall(r'^(?!#)(\S+\.(?:ts|m4s|mp4)\S*)$', t, re.M)[:2]
    d['head'] = t[:300]
    return d


rows = []
# 1) no-DRM：cctv1 全 CDN
for k, tpl in CDN.items():
    u = 'http://%s/ldncctvwbnd/ldcctv1_2/index.m3u8' % (tpl % 'nd')
    d = inspect(u)
    d['cdn'], d['mode'], d['ch'] = k, 'nd', 'cctv1'
    rows.append(d)

# 2) DRM 版对照
for k in ('ali', 'txy'):
    u = 'http://%s/ldncctvwbcd/cdrmldcctv1_1/index.m3u8' % (CDN[k] % 'cd')
    d = inspect(u)
    d['cdn'], d['mode'], d['ch'] = k, 'cdrm', 'cctv1'
    rows.append(d)

with io.open(os.path.join(TMP, 'cctv_cdn_probe.json'), 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

for d in rows:
    print('%-4s %-4s code=%-4s %5dms m3u8=%-5s key=%d' %
          (d['mode'], d['cdn'], d['code'], d['ms'], d['m3u8'], len(d['key'])))
    if d['key']:
        print('      KEY:', d['key'][0][:150])
    if d['variant']:
        print('      VAR:', d['variant'][0][:100])
    if d['seg']:
        print('      SEG:', d['seg'][0][:110])
print('-> tmp/cctv_cdn_probe.json')
