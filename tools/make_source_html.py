# -*- coding: utf-8 -*-
"""生成可交互 HTML 版「IPTV 源成功表」：报表/iptv_源表.html

实测一律取移动网络（tmp/phone_rates_all.tsv + tmp/phone_best.tsv）。
"""
import sys, io, os, json
from urllib.parse import urlsplit
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_source_table import HOST_META, FIND_WAY, meta_for  # noqa

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR = os.path.join(BASE, 'output', 'curated.txt')
OUT = os.path.join(os.path.dirname(BASE), '报表', 'iptv_源表.html')

GAP = [
    ('CCTV-16', '仅 gmxw.7766.org:808/hls/169，3 轮 min 2.18', '单点，个人动态域名，无替补'),
    ('海南卫视', '仅 125.93.74.27:9002 一条', '独家单点，该机倒即归零'),
    ('内蒙古卫视', '仅 play1-qk.nmtv.cn 一条', '单点无备用'),
    ('新疆 / 江西 / 西藏 / 广州综合', '各 1 条源', '单点无备用'),
    ('湖北本地 7 台', '长江云 CDN 全 403（auth_key 约 1 小时轮换）', '模板占位，无源'),
    ('东方 / 香港 / 广东卫视', '移动侧 3 轮全无（已从订阅移除）', '本轮删除，需重找'),
]

CHANS = OrderedDict()
group = ''
with open(CUR, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or ',' not in line:
            continue
        name, url = line.split(',', 1)
        if url == '#genre#':
            group = name
            continue
        CHANS.setdefault(name, {'g': group, 'u': []})['u'].append(url)

def _load_3r():
    """{(台名, URL): (min, avg, max, 判定)} —— 合并首选与候选两份 3 轮结果"""
    m = {}
    for fn in ('phone_rates_3r.tsv', 'cand_rates_3r.tsv'):
        p = os.path.join(BASE, 'tmp', fn)
        if not os.path.exists(p):
            continue
        for line in io.open(p, encoding='utf-8'):
            if line.startswith('#') or not line.strip():
                continue
            c = line.rstrip('\n').split('\t')
            if len(c) >= 7:
                m[(c[0], c[6])] = (float(c[1]), float(c[2]), float(c[3]), c[4])
    return m


R3 = _load_3r()

# 每条线路的实测（用于主机可用率统计）
lines = [{'u': u, 'fl': v[3]} for (n, u), v in R3.items()]

# 每台的首选实测 + 最优替补
phone = {}
for _name, _info in CHANS.items():
    _urls = _info['u']
    _cur = R3.get((_name, _urls[0]))
    _best = None
    for _u in _urls[1:]:
        _r = R3.get((_name, _u))
        if _r and (_best is None or _r[0] > _best[0]):
            _best = (_r[0], _u)
    if _cur:
        phone[_name] = {'p': _cur[0], 'pf': _cur[3],
                        'b': _best[0] if _best else None,
                        'bu': _best[1] if _best else '',
                        'same': _best is None}

rows = []
for name, info in CHANS.items():
    urls = info['u']
    ph = urlsplit(urls[0]).netloc
    meta = meta_for(ph)
    p = phone.get(name)
    bhost = urlsplit(p['bu']).netloc if (p and p['bu']) else ''
    rows.append({
        'n': name, 'g': info['g'], 'h': ph, 'k': meta[0], 'o': meta[1],
        'f': FIND_WAY[meta[3]][0], 'u': urls,
        'r': round(p['p'], 2) if p else None, 'fl': p['pf'] if p else '',
        'b': round(p['b'], 2) if (p and p['b'] is not None) else None, 'bh': bhost,
        'bsame': (p['same'] if p else True),
        'bk': sorted({urlsplit(u).netloc for u in urls[1:]}),
    })

hosts = OrderedDict()
for r in rows:
    for i, u in enumerate(r['u']):
        hk = urlsplit(u).netloc
        h = hosts.setdefault(hk, {'p': [], 'b': [], 'n': 0})
        h['n'] += 1
        (h['p'] if i == 0 else h['b']).append(r['n'])

hstat = {}
for r in lines:
    hk = urlsplit(r['u']).netloc
    s = hstat.setdefault(hk, {'ok': 0, 'weak': 0, 'dead': 0})
    s['ok' if r['fl'] == 'OK' else ('weak' if r['fl'] == '弱' else 'dead')] += 1

host_list = []
for hk, h in hosts.items():
    meta = meta_for(hk)
    cover = [r['n'] for r in rows if hk in {urlsplit(u).netloc for u in r['u']}]
    s = hstat.get(hk)
    host_list.append({'h': hk, 'k': meta[0], 'o': meta[1], 'tpl': meta[2],
                      'way': FIND_WAY[meta[3]][0], 'cover': cover,
                      'p': len(h['p']), 'n': h['n'],
                      'ok': s['ok'] if s else 0,
                      'tot': (s['ok'] + s['weak'] + s['dead']) if s else 0})
host_list.sort(key=lambda x: (-len(x['cover']), x['h']))

dups = []
for name, info in CHANS.items():
    seen = OrderedDict()
    for u in info['u']:
        sp = urlsplit(u)
        seen.setdefault((sp.netloc, sp.path), []).append(u)
    for (nk, path), us in seen.items():
        if len(us) > 1:
            dups.append({'n': name, 'h': nk, 'p': path, 'c': len(us)})

# 移动侧结论
deadp = [{'n': n, 'h': urlsplit(CHANS[n]['u'][0]).netloc, 'b': v['b'],
          'bh': urlsplit(v['bu']).netloc if v['bu'] else ''}
         for n, v in phone.items() if v['pf'] == '死']
better = [{'n': r['n'], 'p': r['r'], 'b': r['b'], 'bh': r['bh']}
          for r in rows if r['r'] is not None and not r['bsame']
          and r['b'] is not None and r['b'] >= 2.0
          and (r['b'] > 2 * r['r'] or r['r'] < 0.5)]

DATA = {'rows': rows, 'hosts': host_list, 'gap': GAP, 'dups': dups,
        'deadp': deadp, 'better': better,
        'lines': {'ok': sum(1 for r in lines if r['fl'] == 'OK'),
                  'weak': sum(1 for r in lines if r['fl'] == '弱'),
                  'dead': sum(1 for r in lines if r['fl'] == '死'),
                  'tot': len(lines)},
        'ways': [{'k': k, 't': v[0], 'd': v[1]} for k, v in FIND_WAY.items()]}

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPTV 直播源完整成功表（移动侧实测）</title>
<style>
:root{
  --bg:#f6f7f9; --panel:#ffffff; --line:#e3e6ea; --tx:#1c2024; --tx2:#5b636d;
  --tx3:#8b939d; --accent:#1f6feb; --accent-soft:#eaf1fe;
  --c1:#0f8a5f; --c1s:#e6f5ee; --c2:#1f6feb; --c2s:#eaf1fe;
  --c3:#b06000; --c3s:#fdf1e0; --c4:#8a4fbf; --c4s:#f3ecfb;
  --red:#c62828; --reds:#fdeaea;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
  font:14px/1.55 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1340px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 6px;letter-spacing:.2px}
.sub{color:var(--tx2);font-size:13px;margin-bottom:20px;line-height:1.7}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:22px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:24px;font-weight:650;line-height:1.2}
.stat span{color:var(--tx3);font-size:12px}
.stat.warn b{color:var(--red)} .stat.warn{background:var(--reds);border-color:#f6d5d5}
.tabs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}
.tab{padding:7px 14px;border-radius:8px;border:1px solid var(--line);background:var(--panel);
  color:var(--tx2);cursor:pointer;font-size:13px}
.tab.on{background:var(--tx);color:#fff;border-color:var(--tx)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.toolbar{display:flex;gap:8px;padding:12px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
input[type=search],select{padding:7px 10px;border:1px solid var(--line);border-radius:7px;
  font-size:13px;background:#fff;color:var(--tx);outline:none}
input[type=search]{flex:1;min-width:180px}
input[type=search]:focus,select:focus{border-color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:9px 12px;background:#fafbfc;color:var(--tx2);font-weight:600;
  font-size:12px;border-bottom:1px solid var(--line);position:sticky;top:0;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid #f0f2f4;vertical-align:top}
tr.row:hover{background:#fafbfc}
tr.row{cursor:pointer}
.ch{font-weight:600;white-space:nowrap}
.host{font-family:var(--mono);font-size:12px;color:var(--tx2);white-space:nowrap}
.badge{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11px;white-space:nowrap}
.b1{background:var(--c1s);color:var(--c1)} .b2{background:var(--c2s);color:var(--c2)}
.b3{background:var(--c3s);color:var(--c3)} .b4{background:var(--c4s);color:var(--c4)}
.muted{color:var(--tx3);font-size:12px}
.num{font-variant-numeric:tabular-nums}
.v-ok{color:var(--c1);font-weight:600} .v-weak{color:var(--c3);font-weight:600}
.v-dead{color:var(--red);font-weight:600}
.detail{display:none;background:#fbfcfd}
.detail td{padding:4px 12px 12px 12px}
.detail ul{margin:6px 0 0;padding:0;list-style:none}
.detail li{font-family:var(--mono);font-size:11.5px;color:var(--tx2);padding:3px 0;
  word-break:break-all;border-bottom:1px dashed #eef0f2}
.detail li:last-child{border:0}
.detail li.prim{color:var(--tx);font-weight:600}
.detail li .tag{font-family:inherit;font-size:10px;background:var(--accent-soft);
  color:var(--accent);padding:1px 5px;border-radius:4px;margin-right:6px;font-weight:600}
.bar{height:5px;background:#eef1f4;border-radius:3px;overflow:hidden;margin-top:4px;min-width:60px}
.bar i{display:block;height:100%;background:var(--c1)}
.way{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff}
.way h4{margin:0 0 6px;font-size:14px}
.way p{margin:0;color:var(--tx2);font-size:13px}
.way .lvl{display:inline-block;font-size:11px;font-weight:700;color:#fff;background:var(--tx);
  border-radius:4px;padding:1px 6px;margin-right:8px}
.gap{width:100%;border-collapse:collapse;font-size:13px}
.gap td{padding:10px 12px;border-bottom:1px solid #f0f2f4}
.sec-t{font-size:13px;font-weight:600;padding:12px 12px 4px}
.empty{padding:30px;text-align:center;color:var(--tx3)}
footer{margin-top:22px;color:var(--tx3);font-size:12px;line-height:1.7}
code{font-family:var(--mono);font-size:12px;background:#f2f4f6;padding:1px 5px;border-radius:4px}
</style>
</head>
<body>
<div class="wrap">
  <h1>IPTV 直播源完整成功表</h1>
  <div class="sub">数据源 <code>output/curated.txt</code>（__NCH__ 台 / __NLINE__ 行）｜ 目标网络：湖北移动<br>
    <b>实测网络</b>：手机 WiFi <code>bg2025</code> → 出口 <code>111.46.161.239</code>（中国湖北孝感·移动），3 轮 × 4 秒采样，逐条解析到 .ts 分片计时，判定取 min</div>
  <div class="stats" id="stats"></div>

  <div class="tabs">
    <div class="tab on" data-t="chan">频道总表</div>
    <div class="tab" data-t="host">按来源合并</div>
    <div class="tab" data-t="way">查找思路</div>
    <div class="tab" data-t="gap">实测结论与缺口</div>
  </div>

  <div class="panel" id="p-chan">
    <div class="toolbar">
      <input type="search" id="q" placeholder="搜索频道 / 主机 / 地址…">
      <select id="fg"><option value="">全部分组</option></select>
      <select id="fk"><option value="">全部来源类别</option></select>
      <select id="fs"><option value="">全部状态</option><option>OK</option><option>弱</option><option>死</option></select>
    </div>
    <table>
      <thead><tr><th style="width:34px">#</th><th style="width:110px">频道</th>
      <th style="width:200px">首选主机</th><th style="width:140px">来源类别</th>
      <th style="width:130px">归属</th><th style="width:76px">移动实测</th>
      <th style="width:170px">移动侧最优</th><th style="width:52px">源数</th>
      <th>查找方式</th></tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>

  <div class="panel" id="p-host" style="display:none">
    <div class="toolbar"><span class="muted" style="padding:6px 2px">
      同一主机的所有频道合并为一行；点行展开覆盖频道清单。按覆盖台数降序。</span></div>
    <table>
      <thead><tr><th style="width:220px">主机</th><th style="width:160px">来源类别</th>
      <th style="width:140px">归属</th><th style="width:150px">路径模板</th>
      <th style="width:80px">覆盖</th><th style="width:60px">首选</th>
      <th style="width:110px">移动侧可用</th><th>频道</th></tr></thead>
      <tbody id="tb2"></tbody>
    </table>
  </div>

  <div class="panel" id="p-way" style="display:none;padding:16px">
    <div id="ways"></div>
    <div class="way"><h4>验证纪律（比找源更重要）</h4>
      <p>① 编号只信「源里标注过」或「多台交叉验证过」，其余一律抓帧看台标——串台成本远高于多花 5 分钟。<br>
         ② 置首需连测 3 轮，判定取 min（最差那轮），不看 max/avg。本表即移动侧 3 轮结果，已据此重排。<br>
         ③ 双网交叉：本机电信 + 手机移动各 3 轮，两边矛盾就不动。<br>
         ④ 判死阈值 0.1 Mbps（死链）≠ 卫视质量线 2.0 Mbps，混用会误杀网关标清流。</p></div>
  </div>

  <div class="panel" id="p-gap" style="display:none;padding:6px 4px">
    <div class="sec-t">首选在移动网络下不可用（必须换源）</div>
    <table class="gap" id="tbd"></table>
    <div class="sec-t">首选可用但不是移动侧最优（建议重排，不急）</div>
    <table class="gap" id="tbb"></table>
    <div class="sec-t">缺口与单点</div>
    <table class="gap" id="tbg"></table>
    <div class="sec-t">冗余线路（同主机同编号，只差 query，可清理）</div>
    <table class="gap" id="tbdp"></table>
  </div>

  <footer>
    重生成：<code>python tools/make_source_table.py</code>（Markdown） ·
    <code>python tools/make_source_html.py</code>（本页）<br>
    网关/个人源随时可能关停，仅个人自用，不公开分发。
  </footer>
</div>
<script>
const D = __DATA__;
const KB = {'广电官方CDN':'b1','广电官方CDN(阿里云)':'b1','广电官方CDN(百视通)':'b1',
 '广电官方CDN(腾讯云)':'b1','广电官方CDN(芒果TV)':'b1','省台自建HLS':'b1',
 '省级IPTV转发(tsfile)':'b2','newlive转发网关':'b3','个人DDNS转发(tsfile)':'b4',
 '个人小站HLS':'b4','境外台官网代理':'b4','短视频CDN(非直播)':'b4'};
const cls = k => KB[k] || 'b4';
const vcls = f => f==='OK'?'v-ok':(f==='弱'?'v-weak':'v-dead');

document.getElementById('stats').innerHTML = [
 [D.rows.length,'频道'],
 [D.lines.tot,'实测线路'],
 [D.lines.ok+' / '+D.lines.tot,'移动侧 OK 线路'],
 [D.rows.filter(r=>r.fl==='死').length,'首选不可用',1],
 [D.rows.filter(r=>r.fl==='弱').length,'首选偏弱',1],
 [D.better.length,'建议换源'],
 [D.hosts.length,'来源主机']
].map(([n,t,w])=>`<div class="stat${w?' warn':''}"><b>${n}</b><span>${t}</span></div>`).join('');

const tb = document.getElementById('tb');
function render(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  const fg = document.getElementById('fg').value, fk = document.getElementById('fk').value;
  const fs = document.getElementById('fs').value;
  let html = '', i = 0;
  D.rows.forEach(r=>{
    if (fg && r.g !== fg) return;
    if (fk && r.k !== fk) return;
    if (fs && r.fl !== fs) return;
    if (q && !(r.n+' '+r.h+' '+r.u.join(' ')).toLowerCase().includes(q)) return;
    i++;
    const rt = r.r===null ? '<span class="muted">-</span>'
      : `<span class="${vcls(r.fl)}">${r.r}</span>`;
    const bs = (!r.bsame && r.b!==null && r.b>=2 && (r.b>2*r.r || r.r<0.5))
      ? `<span class="v-ok">${r.b}</span> <span class="host">@${r.bh}</span>`
      : '<span class="muted">—</span>';
    html += `<tr class="row" data-i="${i}"><td class="num muted">${i}</td>
      <td class="ch">${r.n}</td>
      <td class="host">${r.h}</td>
      <td><span class="badge ${cls(r.k)}">${r.k}</span></td>
      <td class="muted">${r.o}</td>
      <td class="num">${rt}</td>
      <td>${bs}</td>
      <td class="num">${r.u.length}</td>
      <td class="muted">${r.f}</td></tr>
      <tr class="detail" id="d${i}"><td colspan="9"><ul>` +
      r.u.map((u,j)=>`<li class="${j===0?'prim':''}">${j===0?'<span class="tag">首选</span>':''}${u}</li>`).join('') +
      `</ul></td></tr>`;
  });
  tb.innerHTML = html || '<tr><td colspan="9" class="empty">无匹配结果</td></tr>';
  tb.querySelectorAll('tr.row').forEach(tr=>tr.onclick=()=>{
    const d = document.getElementById('d'+tr.dataset.i);
    d.style.display = d.style.display==='table-row' ? 'none' : 'table-row';
  });
}
const maxCov = Math.max(...D.hosts.map(h=>h.cover.length));
document.getElementById('tb2').innerHTML = D.hosts.map((h,i)=>{
  const rate = h.tot ? `${h.ok}/${h.tot}` : '-';
  return `<tr class="row" data-i="h${i}"><td class="host" style="color:var(--tx);font-weight:600">${h.h}</td>
  <td><span class="badge ${cls(h.k)}">${h.k}</span></td>
  <td class="muted">${h.o}</td>
  <td class="host">${h.tpl}</td>
  <td class="num">${h.cover.length}<div class="bar"><i style="width:${h.cover.length/maxCov*100}%"></i></div></td>
  <td class="num">${h.p}</td>
  <td class="num ${h.tot&&h.ok/h.tot>=0.8?'v-ok':(h.tot&&h.ok/h.tot>=0.5?'v-weak':'v-dead')}">${rate}</td>
  <td class="muted">${h.cover.join('、')}</td></tr>
  <tr class="detail" id="dh${i}"><td colspan="8"><ul>
    <li>覆盖 ${h.cover.length} 台，其中 ${h.p} 台以它为首选；共 ${h.n} 条线路</li>
    <li>移动侧实测 OK ${h.ok} / 共 ${h.tot} 条</li>
    <li>发现方式：${h.way}</li></ul></td></tr>`;
}).join('');
document.querySelectorAll('#tb2 tr.row').forEach(tr=>tr.onclick=()=>{
  const d = document.getElementById('d'+tr.dataset.i);
  d.style.display = d.style.display==='table-row' ? 'none' : 'table-row';
});
document.getElementById('ways').innerHTML = D.ways.map((w,i)=>`
  <div class="way"><h4><span class="lvl">L${i+1}</span>${w.t}</h4><p>${w.d}</p></div>`).join('');

document.getElementById('tbd').innerHTML =
  '<tr><th>频道</th><th>首选主机</th><th>移动实测</th><th>移动侧最优</th><th>处理</th></tr>' +
  D.deadp.map(d=>{
    const alt = d.b>=2 ? `<span class="v-ok">${d.b}</span> <span class="host">@${d.bh}</span>` : '<span class="v-dead">无可用替补</span>';
    return `<tr><td class="ch">${d.n}</td><td class="host">${d.h}</td>
      <td class="v-dead">死</td><td>${alt}</td>
      <td class="muted">${d.b>=2?'换首选':'需新找源'}</td></tr>`;}).join('');

document.getElementById('tbb').innerHTML =
  '<tr><th>频道</th><th>首选实测</th><th>移动侧最优</th><th>提升</th></tr>' +
  D.better.map(b=>`<tr><td class="ch">${b.n}</td>
    <td class="num ${b.p<2?'v-weak':'v-ok'}">${b.p}</td>
    <td><span class="v-ok">${b.b}</span> <span class="host">@${b.bh}</span></td>
    <td class="num muted">×${(b.p>0.05?(b.b/b.p):99).toFixed(1)}</td></tr>`).join('');

document.getElementById('tbg').innerHTML = '<tr><th>频道</th><th>现状</th><th>风险</th></tr>' +
  D.gap.map(g=>`<tr><td class="ch">${g[0]}</td><td class="muted">${g[1]}</td><td class="muted">${g[2]}</td></tr>`).join('');

document.getElementById('tbdp').innerHTML = D.dups.length
  ? '<tr><th>频道</th><th>主机</th><th>路径</th><th>条数</th></tr>' +
    D.dups.map(d=>`<tr><td class="ch">${d.n}</td><td class="host">${d.h}</td>
      <td class="host">${d.p}</td><td class="num">${d.c}</td></tr>`).join('')
  : '<tr><td class="muted" style="padding:10px 12px">无重复线路</td></tr>';

[...new Set(D.rows.map(r=>r.g))].forEach(g=>{
  document.getElementById('fg').insertAdjacentHTML('beforeend',`<option>${g}</option>`)});
[...new Set(D.rows.map(r=>r.k))].forEach(k=>{
  document.getElementById('fk').insertAdjacentHTML('beforeend',`<option>${k}</option>`)});
['q','fg','fk','fs'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  t.classList.add('on');
  ['chan','host','way','gap'].forEach(k=>{
    document.getElementById('p-'+k).style.display = (k===t.dataset.t)?'':'none'});
});
</script>
</body>
</html>'''

out = HTML.replace('__DATA__', json.dumps(DATA, ensure_ascii=False))
out = out.replace('__NCH__', str(len(CHANS)))
out = out.replace('__NLINE__', str(sum(len(v['u']) for v in CHANS.values())))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write(out)
print('html ->', OUT, len(out), 'chars')
print('rows=%d hosts=%d dead=%d better=%d' % (len(rows), len(host_list), len(deadp), len(better)))
