# -*- coding: utf-8 -*-
"""探测央视频（yangshipin.cn）网页端直播流的获取方式与加密情况。

输出落 tmp/ysp_probe.json，屏幕只打结论行。
"""
import io
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')
os.makedirs(TMP, exist_ok=True)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url, timeout=20, referer=None, headers=None, data=None):
    h = {'User-Agent': UA, 'Accept': '*/*',
         'Accept-Language': 'zh-CN,zh;q=0.9'}
    if referer:
        h['Referer'] = referer
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001
        return -1, {}, str(e).encode()


def head_only(url, timeout=15):
    """用 Range 请求探活 + 看 content-type，不下整个文件。"""
    h = {'User-Agent': UA, 'Range': 'bytes=0-2047'}
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.headers.get('Content-Type'), r.read(512)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type'), b''
    except Exception as e:  # noqa: BLE001
        return -1, str(e), b''


out = {}

# 1) 直播页 HTML，看有没有内嵌 api 端点 / pid
PAGES = {
    'tv_home': 'https://www.yangshipin.cn/tv/home',
    'cctv1': 'https://www.yangshipin.cn/tv/home?pid=600001859',
}
for k, u in PAGES.items():
    code, hd, body = get(u)
    txt = body.decode('utf-8', 'replace')
    out[k] = {
        'url': u, 'code': code, 'bytes': len(body),
        'has_pid': '600001859' in txt,
        'api_hits': sorted(set(re.findall(r'https?://[a-z0-9.\-]*yangshipin\.cn/[a-zA-Z0-9/_\-]*api[a-zA-Z0-9/_\-]*', txt)))[:15],
        'm3u8_in_html': re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', txt)[:5],
    }

# 2) 央视频直播流接口（网页端常用 pomodoro）
API_TRIES = [
    ('pomodoro_live',
     'https://pomodoro.yangshipin.cn/api/play/v1/live/get_live_stream'
     '?pid=600001859&guid=abcd1234abcd1234abcd1234abcd1234&client=web&vid=&stream_type=1'),
    ('pomodoro_live2',
     'https://pomodoro.yangshipin.cn/api/play/v1/live/get_live_stream'
     '?pid=600001859&guid=abcd1234abcd1234abcd1234abcd1234&client=web'),
    ('cctv_cnapi',
     'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid=600001859'),
]
for k, u in API_TRIES:
    code, hd, body = get(u, referer='https://www.yangshipin.cn/')
    snippet = body.decode('utf-8', 'replace')[:600]
    out[k] = {'url': u, 'code': code, 'bytes': len(body), 'body': snippet}

# 3) 央视网公开直播接口（另一条独立路线）
CNTV = 'https://cctvcnch5c.vdn.live.cntv.cn/api2/live_hd.jsp?pid=cctv1'
code, hd, body = get(CNTV)
out['cntv_live_hd'] = {'url': CNTV, 'code': code, 'bytes': len(body),
                       'body': body.decode('utf-8', 'replace')[:600]}

with io.open(os.path.join(TMP, 'ysp_probe.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

for k, v in out.items():
    print('== %-16s code=%s bytes=%s' % (k, v['code'], v['bytes']))
    if 'body' in v:
        print('   ', v['body'][:260].replace('\n', ' '))
    if 'api_hits' in v:
        print('    api:', v['api_hits'][:4])
        print('    m3u8:', v['m3u8_in_html'][:2])
print('-> tmp/ysp_probe.json')
