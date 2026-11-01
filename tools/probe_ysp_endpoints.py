# -*- coding: utf-8 -*-
"""试探央视频取流端点的准入条件：哪个端点不需要登录 cookie。

只关心：有没有返回 playurl。
"""
import binascii
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')

spec = importlib.util.spec_from_file_location('ysp', os.path.join(BASE, 'tools', 'ysp_live.py'))
ysp = importlib.util.module_from_spec(spec)
_argv, sys.argv = sys.argv, ['x']
spec.loader.exec_module(ysp)
sys.argv = _argv

op = ysp.op
VID, PID = '2000210103', '600001859'
TT = int(time.time())
CKEY = ysp.make_ckey(VID, TT)
GUID = ysp.GUID

tests = []


def try_call(name, url, headers=None, data=None, method=None):
    h = {'User-Agent': ysp.UA_M, 'Referer': ysp.REF, 'Accept': '*/*'}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    t0 = time.time()
    try:
        r = op.open(req, timeout=18)
        raw = r.read().decode('utf-8', 'replace')
        code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        code = e.code
    except Exception as e:  # noqa: BLE001
        raw = str(e)
        code = -1
    hit = '"playurl"' in raw or "'playurl'" in raw or 'playurl' in raw
    tests.append({'name': name, 'code': code, 'ms': int((time.time() - t0) * 1000),
                  'playurl': hit, 'body': raw[:300]})


# 1) 新版 player-api：GET，带 Yspappid，无 signature
p = {
    'adjust': 1, 'appVer': 'V1.0.0', 'app_version': 'V1.0.0', 'cKey': CKEY,
    'channel': 'ysp_tx', 'cmd': 2, 'cnlid': VID, 'defn': 'fhd',
    'devid': 'devid', 'dtype': 1, 'encryptVer': '8.1', 'guid': GUID,
    'otype': 'ojson', 'platform': ysp.PLATFORM, 'rand_str': TT,
    'sphttps': 1, 'stream': 2,
}
u1 = 'https://player-api.yangshipin.cn/v1/player/get_live_info?' + urllib.parse.urlencode(p)
try_call('playerapi_nosign', u1, {'Yspappid': '519748109'})

# 2) 同上 + signature（salt 未知，先试空串）
p2 = dict(p)
p2['signature'] = hashlib.md5((urllib.parse.urlencode(p) + '').encode()).hexdigest()
u2 = 'https://player-api.yangshipin.cn/v1/player/get_live_info?' + urllib.parse.urlencode(p2)
try_call('playerapi_sig_empty', u2, {'Yspappid': '519748109'})

# 3) 旧 liveinfo：带 otype=ojson（拿纯 JSON 而不是 JSONP）
p3 = dict(p)
p3.update({'cmd': 2, 'cnlid': VID, 'livepid': PID, 'defn': 'auto',
           'sdtfrom': 113, 'logintype': 1, 'vip_status': 1,
           'fntick': TT, 'tm': TT, 'flowid': 'a' * 32, 'uhd_flag': 4})
u3 = 'https://liveinfo.yangshipin.cn/?' + urllib.parse.urlencode(p3)
try_call('liveinfo_ojson', u3, {'Cookie': 'guid=%s' % GUID})

# 4) 旧 liveinfo：换一个新鲜 guid（模拟首次访问）
p4 = dict(p3)
p4['guid'] = 'ko7djb70_' + binascii.b2a_hex(os.urandom(9)).decode()
u4 = 'https://liveinfo.yangshipin.cn/?' + urllib.parse.urlencode(p4)
try_call('liveinfo_newguid', u4, {'Cookie': 'guid=%s' % p4['guid']})

with io.open(os.path.join(TMP, 'ysp_endpoints.json'), 'w', encoding='utf-8') as f:
    json.dump(tests, f, ensure_ascii=False, indent=1)

for t in tests:
    print('%-20s %4s %5dms playurl=%-5s %s' %
          (t['name'], t['code'], t['ms'], t['playurl'],
           t['body'][:130].replace('\n', ' ')))
print('-> tmp/ysp_endpoints.json')
