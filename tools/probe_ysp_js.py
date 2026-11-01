# -*- coding: utf-8 -*-
"""从央视频网页的 JS 包里反查直播流接口调用格式。

输出 tmp/ysp_js_hits.txt（命中片段），屏幕只打结论。
"""
import io
import os
import re
import ssl
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')
os.makedirs(TMP, exist_ok=True)

# 只走直连：央视频是国内域名，走代理反而 502
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
op.addheaders = [('User-Agent',
                  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'),
                 ('Referer', 'https://www.yangshipin.cn/')]
ssl._create_default_https_context = ssl._create_unverified_context


def fetch(u, timeout=25):
    try:
        r = op.open(u, timeout=timeout)
        return r.status, r.read()
    except Exception as e:  # noqa: BLE001
        return -1, str(e).encode()


code, body = fetch('https://www.yangshipin.cn/tv/home')
html = body.decode('utf-8', 'replace')
print('page', code, len(body))

srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
print('scripts:', len(srcs))
for s in srcs[:12]:
    print('  ', s[:120])

hits = []
for s in srcs:
    u = s if s.startswith('http') else ('https://www.yangshipin.cn' + ('' if s.startswith('/') else '/') + s)
    c, b = fetch(u)
    t = b.decode('utf-8', 'replace')
    if c != 200:
        print('  FAIL', c, u[:90])
        continue
    print('  ok %8d %s' % (len(t), u[:90]))
    for pat in ('cctvh5-openapi', 'get_live_stream', 'pomodoro', 'live_stream',
                'm3u8', 'auth_key', 'playurl', 'get_live'):
        for m in re.finditer(pat, t):
            a = max(0, m.start() - 160)
            hits.append('### %s @ %s\n%s\n' % (pat, u, t[a:m.start() + 220]))

with io.open(os.path.join(TMP, 'ysp_js_hits.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(hits))

print('hits', len(hits), '-> tmp/ysp_js_hits.txt')
seen = set()
for h in hits:
    k = h.split('\n')[0]
    if k in seen:
        continue
    seen.add(k)
    print('---', k[:110])
