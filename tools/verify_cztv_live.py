#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 cztv CDN 编号是否真在直播。

判据三条，全过才算活：
  1. m3u8 里最后一个分片能 200 拉到，且字节数 > 20KB（几十 k 的假分片不算）
  2. 间隔 12 秒再取一次 m3u8，MEDIA-SEQUENCE 必须增长（滚动 = 真直播）
  3. 分片能被 ffprobe 识别出视频流（排除错误页/纯音频/垃圾数据）

输出 tmp/cztv_live.json + 屏幕汇总
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HOST = 'http://ali-m-l.cztv.com/channels/lantian/channel%02d/1080p.m3u8'
NUMS = list(range(1, 22))          # 已扫出 1~21（缺 11 也一起试）


def fetch(url, timeout=10, limit=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'okhttp/3.12.0'})
    r = OPENER.open(req, timeout=timeout)
    data = r.read() if limit is None else r.read(limit)
    return r.getcode(), data


def parse_m3u8(text):
    seq = None
    m = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', text)
    if m:
        seq = int(m.group(1))
    segs = [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.startswith('#')]
    return seq, segs


def ffprobe_ok(path):
    try:
        p = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name,width,height',
             '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=25)
        out = (p.stdout or '').strip()
        return (out != ''), out
    except Exception as e:
        return False, str(e)


def main():
    results = []
    for n in NUMS:
        url = HOST % n
        rec = {'n': n, 'url': url}
        try:
            c1, d1 = fetch(url)
            t1 = d1.decode('utf-8', 'replace')
            seq1, segs1 = parse_m3u8(t1)
            rec.update({'code1': c1, 'seq1': seq1, 'nseg': len(segs1)})
            if c1 != 200 or not segs1:
                rec['verdict'] = 'no-playlist'
                results.append(rec)
                print('  %-3d 无列表 code=%s' % (n, c1))
                continue

            # 分片：取最后一个（最新）
            seg = segs1[-1]
            seg_url = seg if seg.startswith('http') else \
                url.rsplit('/', 1)[0] + '/' + seg
            rec['seg_url'] = seg_url
            try:
                cs, ds = fetch(seg_url, timeout=20, limit=400000)
                rec['seg_code'] = cs
                rec['seg_bytes'] = len(ds)
            except Exception as e:
                rec['seg_code'] = -1
                rec['seg_bytes'] = 0
                rec['seg_err'] = str(e)[:80]

            if rec.get('seg_code') != 200 or rec.get('seg_bytes', 0) < 20000:
                rec['verdict'] = 'seg-dead'
                results.append(rec)
                print('  %-3d 分片死 code=%s bytes=%s'
                      % (n, rec.get('seg_code'), rec.get('seg_bytes')))
                continue

            # 存盘做 ffprobe
            os.makedirs('tmp/cztv_seg', exist_ok=True)
            sp = 'tmp/cztv_seg/%d.ts' % n
            with open(sp, 'wb') as f:
                f.write(ds)
            ok, info = ffprobe_ok(sp)
            rec['probe'] = info[:60]
            if not ok:
                rec['verdict'] = 'not-video'
                results.append(rec)
                print('  %-3d 分片非视频 %s' % (n, info[:40]))
                continue

            # 滚动检测
            time.sleep(12)
            c2, d2 = fetch(url)
            seq2, _ = parse_m3u8(d2.decode('utf-8', 'replace'))
            rec['seq2'] = seq2
            rolling = (seq1 is not None and seq2 is not None and seq2 > seq1)
            rec['rolling'] = rolling
            rec['verdict'] = 'LIVE' if rolling else 'frozen'
            results.append(rec)
            print('  %-3d %-7s seq %s->%s  seg=%dKB  %s'
                  % (n, rec['verdict'], seq1, seq2,
                     rec['seg_bytes'] // 1024, info[:30]))
        except Exception as e:
            rec['verdict'] = 'error'
            rec['err'] = str(e)[:100]
            results.append(rec)
            print('  %-3d 异常 %s' % (n, str(e)[:60]))

    with open('tmp/cztv_live.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    live = [r['n'] for r in results if r.get('verdict') == 'LIVE']
    frozen = [r['n'] for r in results if r.get('verdict') == 'frozen']
    print('\n真直播 %d 个: %s' % (len(live), live))
    print('冻结/死链 %d 个: %s' % (len(results) - len(live),
                                 [r['n'] for r in results
                                  if r.get('verdict') != 'LIVE']))
    print('-> tmp/cztv_live.json')


if __name__ == '__main__':
    main()
