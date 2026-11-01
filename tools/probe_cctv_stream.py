# -*- coding: utf-8 -*-
"""对比两条路线：
  A. 央视网 tv.cctv.com 的公开直播流（普通 HLS？）
  B. 央视频 yangshipin 的流（WASM 播放器）

重点看 m3u8 里有没有 EXT-X-KEY（是否加密）、编码格式、分片类型。
输出 tmp/cctv_stream.json，屏幕只打结论。
"""
import io
import json
import os
import re
import ssl
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')
os.makedirs(TMP, exist_ok=True)

UA_PC = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ssl._create_default_https_context = ssl._create_unverified_context


def fetch(u, referer=None, timeout=20, ua=UA_PC):
    h = {'User-Agent': ua, 'Accept': '*/*'}
    if referer:
        h['Referer'] = referer
    try:
        r = op.open(urllib.request.Request(u, headers=h), timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception as e:  # noqa: BLE001
        return -1, str(e).encode()


res = {}

# ---------- A. 央视网 tv.cctv.com ----------
code, body = fetch('https://tv.cctv.com/live/cctv1/')
html = body.decode('utf-8', 'replace')
res['tv_page'] = {'code': code, 'bytes': len(body)}
guids = re.findall(r'guid\s*[:=]\s*["\']([0-9a-f]{20,40})["\']', html)
pids = re.findall(r'pid\s*[:=]\s*["\']([0-9a-zA-Z]{6,40})["\']', html)
res['tv_page']['guid'] = guids[:3]
res['tv_page']['pid'] = pids[:3]
# 页面里直接出现的 m3u8
res['tv_page']['m3u8'] = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)[:3]

pid = (pids or [''])[0]
if pid:
    api = 'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid=%s' % pid
    c2, b2 = fetch(api, referer='https://tv.cctv.com/')
    t2 = b2.decode('utf-8', 'replace')
    res['cntv_api'] = {'url': api, 'code': c2, 'body': t2[:800]}
    try:
        j = json.loads(t2)
        res['cntv_api']['hls_url'] = j.get('hls_url') or j.get('hls_url_h5') or ''
        res['cntv_api']['chapters'] = len((j.get('video') or {}).get('chapters') or [])
    except Exception:  # noqa: BLE001
        pass

# ---------- 取一条 m3u8 看加密 ----------
def inspect_m3u8(url, referer=None):
    c, b = fetch(url, referer=referer)
    t = b.decode('utf-8', 'replace')
    d = {'url': url, 'code': c, 'bytes': len(b)}
    d['is_m3u8'] = '#EXTM3U' in t
    d['keys'] = re.findall(r'#EXT-X-KEY:([^\n]+)', t)[:4]
    d['encrypted'] = bool(d['keys'])
    d['seg'] = re.findall(r'^#EXTINF:[^\n]*\n([^#\n]+)', t, re.M)[:2]
    d['variant'] = re.findall(r'^(?!#)(\S+\.m3u8.*)$', t, re.M)[:3]
    d['head'] = t[:400]
    return d


targets = []
if res.get('cntv_api', {}).get('hls_url'):
    targets.append(('cntv_hls', res['cntv_api']['hls_url'], 'https://tv.cctv.com/'))
for m in res['tv_page']['m3u8']:
    targets.append(('tvpage_m3u8', m, 'https://tv.cctv.com/'))

res['streams'] = []
for name, u, ref in targets[:4]:
    d = inspect_m3u8(u, ref)
    d['name'] = name
    res['streams'].append(d)

with io.open(os.path.join(TMP, 'cctv_stream.json'), 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)

print('tv.cctv.com page: code=%s bytes=%s' % (code, len(body)))
print('  guid:', guids[:2])
print('  pid :', pids[:2])
print('  m3u8 in html:', res['tv_page']['m3u8'][:2])
if 'cntv_api' in res:
    print('cntv api code=%s hls=%s' % (res['cntv_api']['code'],
                                       res['cntv_api'].get('hls_url', '')[:100]))
for d in res['streams']:
    print('-- %s code=%s m3u8=%s enc=%s' % (d['name'], d['code'], d['is_m3u8'], d['encrypted']))
    if d['keys']:
        print('   KEY:', d['keys'][0][:160])
    if d['seg']:
        print('   SEG:', d['seg'][0][:110])
print('-> tmp/cctv_stream.json')
