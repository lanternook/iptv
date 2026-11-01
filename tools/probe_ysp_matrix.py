# -*- coding: utf-8 -*-
"""矩阵试探 liveinfo 参数：哪个 vid/pid/defn/logintype 组合能返回 playurl。

cKey 已修对（错误码从 32 权限失败 变为 400 server error）。
只打印结果表，明细落 tmp/ysp_matrix.json。
"""
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
_a, sys.argv = sys.argv, ['x']
spec.loader.exec_module(ysp)
sys.argv = _a

op = ysp.op
CKEY_GUID = ysp.GUID

# 候选 vid（央视频直播 cnlid）：老公开列表 + pid 兜底
VIDS = ['2000210103', '600001859', '2000210104', '2000210105']
PIDS = ['600001859']
DEFNS = ['auto', 'fhd']
LOGINTYPES = [1, 0]
STREAMS = [2, 1]

rows = []


def call(vid, pid, defn, lt, stream, tt):
    p = {
        'cmd': 2, 'cnlid': vid, 'pla': 0, 'stream': stream, 'system': 1,
        'appVer': ysp.VER, 'encryptVer': '8.1', 'qq': 0, 'device': 'PC',
        'guid': CKEY_GUID, 'defn': defn, 'host': 'yangshipin.cn',
        'livepid': pid, 'logintype': lt, 'vip_status': 1, 'livequeue': 1,
        'fntick': tt, 'tm': tt, 'sdtfrom': 113, 'platform': ysp.PLATFORM,
        'cKey': ysp.make_ckey(vid, tt), 'queueStatus': 0, 'uhd_flag': 4,
        'flowid': 'a' * 32, 'sphttps': 1,
        'callback': 'txvlive_videoinfoget_%d' % tt,
    }
    u = 'https://liveinfo.yangshipin.cn/?' + urllib.parse.urlencode(p)
    req = urllib.request.Request(u, headers={
        'User-Agent': ysp.UA_M, 'Referer': ysp.REF,
        'Cookie': 'guid=%s' % CKEY_GUID, 'Accept': '*/*'})
    try:
        raw = op.open(req, timeout=15).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return {'vid': vid, 'pid': pid, 'defn': defn, 'lt': lt, 'stream': stream,
                'code': -1, 'err': str(e)[:80], 'playurl': ''}
    iret = ''
    try:
        body = json.loads(raw[raw.index('(') + 1:raw.rindex(')')])
        iret = body.get('iretcode')
        pu = body.get('playurl') or ''
        err = body.get('errinfo', '')
    except Exception:  # noqa: BLE001
        pu, err = '', raw[:100]
    return {'vid': vid, 'pid': pid, 'defn': defn, 'lt': lt, 'stream': stream,
            'iret': iret, 'err': err, 'playurl': pu}


TT = int(time.time())
for vid in VIDS:
    for pid in PIDS:
        for defn in DEFNS:
            for lt in LOGINTYPES:
                for st in STREAMS:
                    r = call(vid, pid, defn, lt, st, TT)
                    rows.append(r)
                    if r.get('playurl'):
                        print('HIT vid=%s defn=%s lt=%s stream=%s -> %s' %
                              (vid, defn, lt, st, r['playurl'][:110]))
TT2 = int(time.time()) + 3
for r in rows[:0]:
    pass

with io.open(os.path.join(TMP, 'ysp_matrix.json'), 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

hits = [r for r in rows if r.get('playurl')]
print('总试 %d 组，命中 %d' % (len(rows), len(hits)))
seen = set()
for r in rows:
    k = (r.get('iret'), r.get('err'))
    if k in seen:
        continue
    seen.add(k)
    print('  iret=%-5s err=%-28s  (vid=%s defn=%s lt=%s st=%s)' %
          (r.get('iret'), str(r.get('err'))[:28], r['vid'], r['defn'], r['lt'], r['stream']))
print('-> tmp/ysp_matrix.json')
