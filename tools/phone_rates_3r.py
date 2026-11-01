# -*- coding: utf-8 -*-
"""把 tools/phone_speed.py 的多轮汇总日志解析成表格数据

用法:
    python tools/phone_rates_3r.py [日志] [输出tsv] [清单(可选,用于补 URL)]
默认:
    日志   tmp/phone_speed_3r.log
    输出   tmp/phone_rates_3r.tsv
    清单   tmp/primary.txt

为什么要解析日志而不是 output/phone_result.txt：
  phone_speed.py 只把**第 1 轮**写进 phone_result.txt（供 apply_phone_speed / --ingest），
  3 轮汇总只打印在屏幕。判定首选必须用 min（手册 §6），所以要吃汇总行。
"""
import io, os, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, 'tmp', 'phone_speed_3r.log')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'tmp', 'phone_rates_3r.tsv')
LIST = sys.argv[3] if len(sys.argv) > 3 else os.path.join(BASE, 'tmp', 'primary.txt')

url_of = {}
if os.path.exists(LIST):
    for line in io.open(LIST, encoding='utf-8'):
        s = line.strip()
        if '|' in s:
            n, u = s.split('|', 1)
            url_of[n] = u

# CCTV-1       OK  min= 12.34 avg= 15.00 max= 18.00   12.34 15.00 18.00
PAT = re.compile(r'^(\S+)\s+(OK|弱|死)\s+min=\s*([\d.]+)\s+avg=\s*([\d.]+)\s+max=\s*([\d.]+)\s*(.*)$')

rows = []
if os.path.exists(LOG):
    for line in io.open(LOG, encoding='utf-8', errors='replace'):
        m = PAT.match(line.strip())
        if not m:
            continue
        name, fl, mn, av, mx, rest = m.groups()
        rows.append((name, float(mn), float(av), float(mx), fl,
                     rest.strip(), url_of.get(name, '')))

if not rows:
    print('未解析到汇总行：%s' % LOG)
    sys.exit(1)

rows.sort(key=lambda r: -r[1])
with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write('# 频道\tmin\tavg\tmax\t判定\t各轮Mbps\tURL\n')
    for r in rows:
        f.write('%s\t%.2f\t%.2f\t%.2f\t%s\t%s\t%s\n' % r)

ok = sum(1 for r in rows if r[4] == 'OK')
weak = [r[0] for r in rows if r[4] == '弱']
dead = [r[0] for r in rows if r[4] == '死']
print('解析 %d 条 -> %s' % (len(rows), OUT))
print('OK %d ｜ 弱 %d: %s' % (ok, len(weak), '、'.join(weak) if weak else '无'))
print('死 %d: %s' % (len(dead), '、'.join(dead) if dead else '无'))
