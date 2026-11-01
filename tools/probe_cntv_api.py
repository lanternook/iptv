#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试央视网老取流接口（getHttpVideoInfo / live.do），直连不走代理。

这些接口 2018~2022 年是公开可用的，返回 m3u8。若仍存活，
就是最干净的官方源：CNTV 自己的 CDN，不经过任何家宽网关。
"""
import json
import urllib.request

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')

CAND = [
    # 经典 XML 接口（flash 时代），channel_1 = CCTV-1
    'http://vdn.live.cntv.cn/api2/live.do?channel=pa:channel_%d&client=flash',
    # 后来的 json 接口，需要 pid
    'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid=%s',
    # 央视网 h5 播放器配置
    'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?channel=%s&client=flash',
]


def get(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        r = OP.open(req, timeout=timeout)
        return r.getcode(), r.read(3000).decode('utf-8', 'replace')
    except Exception as e:
        return -1, str(e)[:90]


def main():
    out = []
    # 1) 老 XML 接口，试 channel_1..5
    for i in range(1, 6):
        u = CAND[0] % i
        c, t = get(u)
        rec = {'url': u, 'code': c, 'len': len(t)}
        rec['has_m3u8'] = '.m3u8' in t
        rec['snippet'] = t[:220].replace('\n', ' ')
        out.append(rec)
        print('[xml %d] code=%s len=%d m3u8=%s' % (i, c, len(t), rec['has_m3u8']))
        if c == 200:
            print('   ', t[:200].replace('\n', ' '))

    # 2) h5 播放器配置页，挖 pid / guid
    for page in ['https://tv.cctv.com/live/cctv1/',
                 'https://tv.cctv.com/live/cctv13/']:
        c, t = get(page, timeout=12)
        rec = {'url': page, 'code': c, 'len': len(t)}
        rec['has_pid'] = 'pid=' in t
        rec['has_guid'] = 'guid' in t
        out.append(rec)
        print('[page] %s code=%s len=%d pid=%s guid=%s'
              % (page, c, len(t), rec['has_pid'], rec['has_guid']))
        if c == 200:
            import re
            for pat in [r'pid\s*[=:]\s*["\']?([0-9A-Za-z]{6,})',
                        r'guid\s*[=:]\s*["\']?([0-9a-f]{8,})',
                        r'(https?://[^\s"\']+\.m3u8[^\s"\']*)']:
                hits = re.findall(pat, t)[:5]
                if hits:
                    print('    %s -> %s' % (pat[:20], hits))

    with open('tmp/cntv_api.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('-> tmp/cntv_api.json')


if __name__ == '__main__':
    main()
