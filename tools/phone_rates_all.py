# -*- coding: utf-8 -*-
"""解析手机（移动网络）全量测速 -> tmp/phone_rates_all.tsv + tmp/phone_best.tsv

输入: tmp/phone_all_raw2.txt  每行 台名|Mbps|httpcode|segbytes
      tmp/phone_all.txt       每行 台名|URL（顺序与测速一致）
输出: tmp/phone_rates_all.tsv  台名\tURL\tmbps\tcode\tbytes\t判定\t是否首选
      tmp/phone_best.tsv       台名\t最优mbps\t最优URL\t首选mbps\t首选URL\t是否一致
"""
import io, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, 'tmp', 'phone_all_raw2.txt')
LIST = os.path.join(BASE, 'tmp', 'phone_all.txt')
OUT_ALL = os.path.join(BASE, 'tmp', 'phone_rates_all.tsv')
OUT_BEST = os.path.join(BASE, 'tmp', 'phone_best.tsv')


def flag(mbps, code):
    if str(code) not in ('200', '206'):
        return '死'
    if mbps < 0.1:
        return '死'
    if mbps < 2.0:
        return '弱'
    return 'OK'


pairs = []
for line in io.open(LIST, encoding='utf-8'):
    s = line.strip()
    if '|' in s:
        n, u = s.split('|', 1)
        pairs.append((n, u))

raw = []
for line in io.open(RAW, encoding='utf-8'):
    s = line.strip()
    if not s or '|' not in s:
        continue
    c = s.split('|')
    if len(c) < 4:
        continue
    try:
        mbps = float(c[1])
    except ValueError:
        mbps = 0.0
    raw.append((c[0], mbps, c[2], c[3]))

# 按顺序对齐（同名多条按出现次序匹配）
rows = []
idx = 0
for name, url in pairs:
    if idx >= len(raw):
        break
    rn, mbps, code, sz = raw[idx]
    idx += 1
    rows.append({'n': name, 'u': url, 'mbps': mbps, 'code': code,
                 'sz': sz, 'fl': flag(mbps, code)})

with io.open(OUT_ALL, 'w', encoding='utf-8', newline='\n') as f:
    f.write('# 频道\tmbps\tcode\tbytes\t判定\t是否首选\tURL\n')
    seen = set()
    for r in rows:
        first = '首选' if r['n'] not in seen else '备用'
        seen.add(r['n'])
        f.write('%s\t%.2f\t%s\t%s\t%s\t%s\t%s\n'
                % (r['n'], r['mbps'], r['code'], r['sz'], r['fl'], first, r['u']))

# 每台最优（只取 OK/弱，死的不选）
best = {}
for r in rows:
    if r['fl'] == '死':
        continue
    cur = best.get(r['n'])
    if cur is None or r['mbps'] > cur['mbps']:
        best[r['n']] = r

with io.open(OUT_BEST, 'w', encoding='utf-8', newline='\n') as f:
    f.write('# 频道\t最优mbps\t最优URL\t首选mbps\t首选URL\t是否一致\n')
    seen = set()
    for r in rows:
        if r['n'] in seen:
            continue
        seen.add(r['n'])
        b = best.get(r['n'])
        same = 'Y' if (b and b['u'] == r['u']) else 'N'
        f.write('%s\t%.2f\t%s\t%.2f\t%s\t%s\n'
                % (r['n'], b['mbps'] if b else 0, b['u'] if b else '',
                   r['mbps'], r['u'], same))

tot = len(rows)
ok = sum(1 for r in rows if r['fl'] == 'OK')
weak = sum(1 for r in rows if r['fl'] == '弱')
dead = sum(1 for r in rows if r['fl'] == '死')
print('线路 %d：OK %d ｜ 弱 %d ｜ 死 %d' % (tot, ok, weak, dead))
print('频道 %d，其中移动侧最优≠首选 %d 台'
      % (len(seen), sum(1 for l in io.open(OUT_BEST, encoding='utf-8')
                        if not l.startswith('#') and l.rstrip().endswith('N'))))
print('->', OUT_ALL)
print('->', OUT_BEST)
