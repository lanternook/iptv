# -*- coding: utf-8 -*-
"""对每台首选源做 N 轮测速，结果落盘 tmp/primary_rates.tsv

用法: python tools/measure_primary.py [轮数] [秒数] [并发]
输出列: 频道\tmin\tavg\tmax\t判定\tURL
注意: 本机为xx电信，结果仅代表电信侧连通性，不代表目标机（xx移动）体验。
"""
import os, sys, io
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import speed_multi as S  # noqa: E402

BASE = os.path.dirname(HERE)
LIST = os.path.join(BASE, 'tmp', 'primary.txt')
OUT = os.path.join(BASE, 'tmp', 'primary_rates.tsv')

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
workers = int(sys.argv[3]) if len(sys.argv) > 3 else 10

items = S.load_items(LIST)
print('共 %d 条，%d 轮，采样 %.0fs，并发 %d' % (len(items), rounds, seconds, workers))
res = S.run(items, rounds, seconds, workers)

rows = []
for i in sorted(res):
    tag, url, v = res[i]
    mn, mx = min(v), max(v)
    av = sum(v) / len(v)
    rows.append((tag, mn, av, mx, S.flag_of(v), url))
rows.sort(key=lambda r: -r[1])

with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write('# 频道\tmin\tavg\tmax\t判定\tURL\n')
    for r in rows:
        f.write('%s\t%.2f\t%.2f\t%.2f\t%s\t%s\n' % r)

weak = [r[0] for r in rows if r[4] != 'OK']
print('落盘 %s ｜ 弱/死 %d: %s' % (OUT, len(weak), ', '.join(weak) if weak else '无'))
