# -*- coding: utf-8 -*-
"""解析手机（移动网络）测速结果 -> tmp/phone_rates.tsv

输入: tmp/phone_raw2.txt   每行 台名|Mbps|httpcode|segbytes
输出: tmp/phone_rates.tsv  台名\tmin\tavg\tmax\t判定\tURL\thttpcode\tbytes
判定（移动侧单轮，4 秒采样）:
    m3u8fail / code!=200 / mbps<0.1  -> 死
    mbps < 2.0                       -> 弱（低于卫视质量线）
    其余                              -> OK
"""
import io, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, 'tmp', 'phone_raw2.txt')
LIST = os.path.join(BASE, 'tmp', 'phone_primary.txt')
OUT = os.path.join(BASE, 'tmp', 'phone_rates.tsv')

url_of = {}
for line in io.open(LIST, encoding='utf-8'):
    s = line.strip()
    if '|' in s:
        n, u = s.split('|', 1)
        url_of[n] = u


def flag(mbps, code, note):
    if note == 'm3u8fail' or str(code) not in ('200', '206'):
        return '死'
    if mbps < 0.1:
        return '死'
    if mbps < 2.0:
        return '弱'
    return 'OK'


rows = []
for line in io.open(RAW, encoding='utf-8'):
    s = line.strip()
    if not s or '|' not in s:
        continue
    c = s.split('|')
    if len(c) < 4:
        continue
    name, sp, code, sz = c[0], c[1], c[2], c[3]
    note = '' if code != '000' else 'm3u8fail'
    try:
        mbps = float(sp)
    except ValueError:
        mbps = 0.0
    rows.append((name, mbps, flag(mbps, code, note if note else ''),
                 url_of.get(name, ''), code, sz))

rows.sort(key=lambda r: -r[1])
with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write('# 频道\tmin\tavg\tmax\t判定\tURL\tcode\tbytes\n')
    for name, mbps, fl, url, code, sz in rows:
        f.write('%s\t%.2f\t%.2f\t%.2f\t%s\t%s\t%s\t%s\n'
                % (name, mbps, mbps, mbps, fl, url, code, sz))

ok = sum(1 for r in rows if r[2] == 'OK')
weak = [r[0] for r in rows if r[2] == '弱']
dead = [r[0] for r in rows if r[2] == '死']
print('解析 %d 条 -> %s' % (len(rows), OUT))
print('OK %d ｜ 弱 %d: %s' % (ok, len(weak), '、'.join(weak) if weak else '无'))
print('死 %d: %s' % (len(dead), '、'.join(dead) if dead else '无'))
