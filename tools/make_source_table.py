# -*- coding: utf-8 -*-
"""从 curated.txt 生成「频道—来源—查找思路」完整成功表（Markdown + JSON）

实测一律取**移动网络 3 轮**（手机 WiFi bg2025 → 湖北孝感移动，phone_speed.py 跑）：
  tmp/phone_rates_3r.tsv   首选源 3 轮 min/avg/max
  tmp/cand_rates_3r.tsv    候选源 3 轮 min/avg/max
判定取 **min**（手册 §6：晚高峰看最差那轮）。

生成：python tools/make_source_table.py
"""
import sys, io, os, json
from urllib.parse import urlsplit
from collections import OrderedDict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR = os.path.join(BASE, 'output', 'curated.txt')
OUT_MD = os.path.join(os.path.dirname(BASE), '报表', 'iptv_源表.md')
OUT_JSON = os.path.join(BASE, 'tmp', 'source_table.json')

NET_LABEL = ('手机 WiFi `bg2025`（出口 111.46.161.239，中国湖北孝感·移动），'
             '3 轮 × 4 秒采样，判定取 min')

HOST_META = {
    '119.125.131.239:9901': ('省级IPTV转发(tsfile)', '广东广州·电信', '/tsfile/live/{NNNN}_1.m3u8?key=txiptv', 'tsfile_enum'),
    '125.93.74.27:9002':    ('省级IPTV转发(tsfile)', '广东东莞·电信', '/tsfile/live/{NNNN}_1.m3u8?key=txiptv&authid=0', 'tsfile_enum'),
    '218.13.170.98:9901':   ('省级IPTV转发(tsfile)', '广东广州·电信', '/tsfile/live/{NNNN}_1.m3u8?key=txiptv', 'tsfile_enum'),
    '153.0.171.163:9901':   ('省级IPTV转发(tsfile)', '海南海口·联通', '/tsfile/live/{NNNN}_1.m3u8?key=txiptv', 'tsfile_enum'),
    '119.39.9.8:9901':      ('省级IPTV转发(tsfile)', '湖南长沙·联通', '/tsfile/live/{NNNN}_1.m3u8', 'tsfile_enum'),
    '112.27.5.218:9901':    ('省级IPTV转发(tsfile)', '广东广州·移动', '/tsfile/live/faacts/{NNNN}_1.m3u8', 'tsfile_enum'),
    '218.84.12.186:8001':   ('省台自建HLS', '新疆·电信', '/hls/main/playlist.m3u8', 'official'),
    'genglei.8866.org:9901':('个人DDNS转发(tsfile)', '动态域名·个人', '/tsfile/live/{NNNN}_1.m3u8?key=txiptv', 'personal'),
    'gmxw.7766.org:808':    ('个人小站HLS', '动态域名·个人', '/hls/{N}/index.m3u8', 'personal'),
    '183.250.156.180:9999': ('newlive转发网关', '广东广州·移动', '/newlive/live/hls/{N}/live.m3u8', 'gateway'),
    '118.122.144.115:8888': ('newlive转发网关', '四川成都·电信', '/newlive/live/hls/{N}/live.m3u8', 'gateway'),
    '219.147.245.238:25480':('newlive转发网关', '黑龙江哈尔滨·电信', '/newlive/live/hls/{N}/live.m3u8', 'gateway'),
    '120.40.39.246:352':    ('newlive转发网关', '福建福州·电信', '/newlive/live/hls/{N}/live.m3u8', 'gateway'),
    'ali-m-l.cztv.com':     ('广电官方CDN(阿里云)', '浙江广电·杭州', '/channels/lantian/channel{NNN}/1080p.m3u8', 'official'),
    'ali-m-l.cztv.com:80':  ('广电官方CDN(阿里云)', '浙江广电·杭州', '/channels/lantian/channel{NNN}/1080p.m3u8', 'official'),
    'ali-xwl.cztv.com':     ('广电官方CDN(阿里云)', '浙江广电·杭州', '/live/channel0NN{720,1080}Plxw.m3u8', 'official'),
    'bp-resource-dfl.bestv.cn': ('广电官方CDN(百视通)', '上海·百视通', '/{port}/3/video.m3u8', 'official'),
    'event.pull.hebtv.com': ('广电官方CDN', '河北广电·石家庄', '/jishi/{name}.m3u8', 'official'),
    'idclive.hljtv.com:4430': ('广电官方CDN', '黑龙江广电·哈尔滨', '/live/hljws_own.m3u8', 'official'),
    'play1-qk.nmtv.cn':     ('广电官方CDN', '内蒙古广电·呼和浩特', '/live/{id}.m3u8', 'official'),
    'tencentplay.gztv.com': ('广电官方CDN(腾讯云)', '广州广播电视台', '/live/zonghes.m3u8?txSecret=...', 'official'),
    'hkstv.tv':             ('境外台官网代理', '香港卫视官网', '/api/m3u8-proxy?url=...', 'official'),
    'dxtx.hntv.tv':         ('广电官方CDN(腾讯云)', '河南广电·郑州', '/live/lypd.m3u8?txSecret=...', 'official'),
    'hlsal-ldvt.qing.mgtv.com': ('广电官方CDN(芒果TV)', '湖南广电·长沙', '/nn_live/nn_x64/{token}/HNWSZGST.m3u8', 'official'),
    'live.zohi.tv':         ('广电官方CDN', '福州广电·福州', '/video/s10001-fztv-3/index.m3u8', 'official'),
    'txmov2.a.kwimgs.com':  ('短视频CDN(非直播)', '抖音/快手CDN', '/upic/...mp4', 'fallback'),
}

FIND_WAY = {
    'official': ('官方站扒源', '打开省台官网/APP 的直播页，开发者工具筛 `.m3u8` 请求，复制完整 URL（含 token 的原样保留）。'),
    'tsfile_enum': ('txiptv 编号枚举', '按 `?key=txiptv` 特征在 GitHub 代码搜索命中同款转发，再用 `enum_hls.py` 从 0001 扫到 0200，逐条抓帧确认台标。'),
    'gateway': ('GitHub 抠网关', '`find_gateway.py` 用代码搜索关键词 `newlive/live/hls`，正则从别人公开的 m3u 里抠 `host:port`，串行验证后进池。'),
    'personal': ('社区源兜底', '从订阅池/公开 m3u 列表里摘出的个人 DDNS 转发，可用但不稳定，只作末位备用。'),
    'fallback': ('全网兜底', '全渠道无直播源时，用短视频 CDN 的静态片段占位（能播但内容不变），仅避免空频道。'),
}


def host_key(url):
    return urlsplit(url).netloc


def meta_for(netloc):
    if netloc in HOST_META:
        return HOST_META[netloc]
    bare = netloc.split(':')[0]
    for k, v in HOST_META.items():
        if k.split(':')[0] == bare:
            return v
    return ('未分类', '未知', '-', 'personal')


def load_3r():
    """{(台名, URL): (min, avg, max, flag)}，合并首选与候选两批 3 轮结果"""
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


def main():
    rates = load_3r()
    chans = OrderedDict()
    cur_group = ''
    with open(CUR, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or ',' not in line:
                continue
            name, url = line.split(',', 1)
            if url == '#genre#':
                cur_group = name
                continue
            chans.setdefault(name, {'group': cur_group, 'urls': []})
            chans[name]['urls'].append(url)

    hosts = OrderedDict()
    for name, info in chans.items():
        for i, url in enumerate(info['urls']):
            hk = host_key(url)
            h = hosts.setdefault(hk, {'primary': [], 'backup': [], 'urls': []})
            h['urls'].append(url)
            (h['primary'] if i == 0 else h['backup']).append(name)

    host_stat = {}
    for (nm, u), r in rates.items():
        hk = host_key(u)
        s = host_stat.setdefault(hk, {'ok': 0, 'weak': 0, 'dead': 0})
        s['ok' if r[3] == 'OK' else ('weak' if r[3] == '弱' else 'dead')] += 1

    rows = []
    for name, info in chans.items():
        urls = info['urls']
        p_host = host_key(urls[0])
        meta = meta_for(p_host)
        p = rates.get((name, urls[0]))
        best = None
        for u in urls:
            r = rates.get((name, u))
            if not r or r[3] == '死':
                continue
            if best is None or r[0] > best[0]:
                best = (r[0], u)
        rows.append({
            'name': name, 'group': info['group'], 'primary_url': urls[0],
            'primary_host': p_host, 'kind': meta[0], 'owner': meta[1],
            'find': FIND_WAY[meta[3]][0], 'n_total': len(urls),
            'p': p, 'best': best,
        })

    json.dump({'rows': [{'name': r['name'], 'group': r['group'],
                         'primary_url': r['primary_url'],
                         'primary_host': r['primary_host'],
                         'kind': r['kind'], 'owner': r['owner'],
                         'find': r['find'], 'n_total': r['n_total'],
                         'p': r['p'], 'best': r['best']} for r in rows]},
              open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    L = []
    L.append('# IPTV 直播源完整成功表\n')
    L.append('> 生成时间：2026-11-01 ｜ 数据源 `output/curated.txt`（%d 台 / %d 行）'
             % (len(chans), sum(len(c['urls']) for c in chans.values())))
    L.append('> 目标网络：湖北移动（Android 盒子 + 手机「我的电视直播版」）')
    L.append('> **实测网络**：%s' % NET_LABEL)
    deadp = [(n, r) for n, r in [(r['name'], r['p']) for r in rows] if r and r[3] == '死']
    weakp = [(n, r) for n, r in [(r['name'], r['p']) for r in rows] if r and r[3] == '弱']
    L.append('> **本轮变更**：已按 3 轮 min 重排，换首选 10 台（含天津卫视「首选近全死→替补接管」）；'
             '删除移动网络下完全无源的 3 台（东方卫视、香港卫视、广东卫视）')
    L.append('> **首选状态**：%d 台 OK ｜ %d 台弱 ｜ %d 台死：%s'
             % (len(rows) - len(deadp) - len(weakp), len(weakp), len(deadp),
                '、'.join(n for n, _ in deadp) if deadp else '无'))
    L.append('')

    L.append('## 一、频道总表（每台首选源 + 移动侧 3 轮实测）\n')
    L.append('> 「移动实测」= 当前首选 URL 的 3 轮 min（Mbps）+ 判定；'
             '「移动侧最优」= 该台全部线路里 min 最高的一条（明显优于首选时才列）。\n')
    L.append('| # | 频道 | 分组 | 首选主机 | 来源类别 | 主机归属 | 移动实测(min) | 移动侧最优 | 备用数 | 查找方式 |')
    L.append('|---|---|---|---|---|---|---|---|---|---|')
    better = []
    for i, r in enumerate(rows, 1):
        p, best = r['p'], r['best']
        cell = '%.2f %s' % (p[0], p[3]) if p else '-'
        bcell = '—'
        if p and best and best[1] != r['primary_url'] and best[0] >= 2.0 \
                and (best[0] > 1.5 * p[0]):
            bcell = '%.2f @`%s`' % (best[0], host_key(best[1]))
            better.append((r['name'], p[0], best[0], host_key(best[1])))
        L.append('| %d | %s | %s | `%s` | %s | %s | %s | %s | %d | %s |'
                 % (i, r['name'], r['group'], r['primary_host'], r['kind'],
                    r['owner'], cell, bcell, r['n_total'] - 1, r['find']))

    L.append('\n## 二、按来源合并（同主机的频道归到一起）\n')
    L.append('> 移动侧可用率 = 该主机在 3 轮实测中 OK 条数 / 实测条数（未测的线路不计）。\n')
    L.append('| 主机 | 类别 | 归属 | 覆盖台数 | 首选台数 | 3轮可用 | 覆盖频道 |')
    L.append('|---|---|---|---|---|---|---|')
    ordered = sorted(hosts.items(), key=lambda kv: -len(kv[1]['urls']))
    for netloc, h in ordered:
        meta = meta_for(netloc)
        cover = [n for n in chans
                 if netloc in {host_key(u) for u in chans[n]['urls']}]
        s = host_stat.get(netloc)
        rate = ('%d/%d' % (s['ok'], s['ok'] + s['weak'] + s['dead'])) if s else '-'
        L.append('| `%s` | %s | %s | %d | %d | %s | %s |'
                 % (netloc, meta[0], meta[1], len(cover), len(h['primary']), rate,
                    '、'.join(cover)))

    L.append('\n## 三、本轮 3 轮实测结论\n')
    L.append('| 项目 | 结果 |')
    L.append('|---|---|')
    L.append('| 首选源 3 轮（52 条） | OK 44 ｜ 弱 5 ｜ 死 3 |')
    L.append('| 候选源 3 轮（26 条） | OK 22 ｜ 弱 4 ｜ 死 0 |')
    L.append('| 换首选 | 10 台（CCTV-3/4/5/9/11/15、天津、江苏、甘肃、宁夏） |')
    L.append('| 删除无源频道 | 3 台（东方卫视、香港卫视、广东卫视） |')
    L.append('')
    L.append('**1. 单轮 vs 3 轮：4 台误判被纠正**\n')
    L.append('单轮曾判「死」的 CCTV-16（2.18）、东南卫视（10.47）、北京卫视（6.80）、'
             '甘肃卫视（2.14），3 轮全部正常 —— 印证手册 §6「一次测速不算数」。\n')
    L.append('**2. 仍偏弱的台（min<2，但有源可用）**\n')
    L.append('| 频道 | min | avg | 说明 |')
    L.append('|---|---|---|---|')
    for n, r in weakp:
        L.append('| %s | %.2f | %.2f | 波动大或码率低，可播 |' % (n, r[0], r[1]))
    L.append('\n**3. 换首选明细**\n')
    L.append('见 `tmp/reorder_report.md`；规则：候选 min ≥ 2.0 且 > 原首选 min × 1.5；'
             '**补充规则**：原首选 min < 0.1（近乎全死）时，替补 min ≥ 1.0 即接管'
             '（天津卫视 0.00 → 1.45 由此触发）。\n')

    L.append('\n### 3.1 查找思路（四类源，按失效速度排序）\n')
    L.append('**总原则：官方 CDN 优先 → 省级转发次之 → 转发网关保底 → 个人源兜底。**\n')
    L.append('| 优先级 | 类别 | 方法 | 工具 | 说明 |')
    L.append('|---|---|---|---|---|')
    L.append('| L1 | 广电官方 CDN | 官方站扒源 | 浏览器开发者工具 + `verify_feed.py` | 省台官网/APP 直播页筛 m3u8，稳定性最好但只覆盖本省台 |')
    L.append('| L2 | 省级 IPTV 转发(tsfile) | txiptv 编号枚举 | `enum_hls.py` / `find_source.py` | 命中 `?key=txiptv` 同款转发后从 0001 扫到 0200，**必须抓帧验台标** |')
    L.append('| L3 | newlive 转发网关 | GitHub 代码搜索抠 host:port | `find_gateway.py` | 一次能补 10~17 个央视台，晚高峰首选入口；寿命按周算 |')
    L.append('| L4 | 个人 DDNS 源 | 社区订阅池摘取 | `merge_tv.py` / `subscribe_pool.txt` | 只作末位备用，随时消失 |')

    L.append('\n### 3.2 编号映射（决定「找到的地址对不对」）\n')
    L.append('| 主机 | 方案 | 央视编号 | 卫视编号 |')
    L.append('|---|---|---|---|')
    L.append('| `119.125.131.239:9901` | 10NN，**1020 被 CCTV-5+ 占用** | 1015~1019=CCTV-1~5；1020=5+；1021~1030=CCTV-6~15；**无 16/17** | 1048~1068，无广东/新疆 |')
    L.append('| `183.250.156.180:9999` | 直编无 5+ | 1~15=CCTV-1~15；**16=404**；17=CCTV-17 | 31=江苏卫视 |')
    L.append('| `118.122.144.115:8888` | 直编 | 1~15 直通；**16=CCTV-5+**；17=CCTV-17 | 20=东南卫视 |')
    L.append('| `219.147.245.238:25480` | 顺移 | 6=5+；7~16=CCTV-6~15；17=CCTV-17，**无 CCTV-16** | - |')
    L.append('| `120.40.39.246:352` | 顺移 | 同上；**CCTV-17 在 18**；本轮有 6 台置首 | 31=江苏卫视 |')

    L.append('\n### 3.3 验证纪律\n')
    L.append('1. **逐帧验台标**：编号规则只信「源里标注过」或「多台交叉验证过」，其余一律 `grab_frames2.py` 抽帧看图。')
    L.append('2. **一次测速不算数**：置首需连测 3 轮，判定取 **min**。本轮已按此执行。')
    L.append('3. **双网交叉**：本机电信只判活，排序一律用手机移动侧数据。')
    L.append('4. **判死阈值 0.1 Mbps（死链）≠ 卫视质量线 2.0 Mbps**，混用会误杀网关标清流。')

    L.append('\n### 3.4 典型发现链路\n')
    L.append('| 目标 | 发现过程 | 结果 |')
    L.append('|---|---|---|')
    L.append('| 央视 + 大部分卫视 | 社区 m3u 出现 `?key=txiptv&playlive=1&down=1` → 判为省级转发 → `enum_hls.py` 1015~1078 → 抓帧确认 | `119.125.131.239:9901` 覆盖 33 台 |')
    L.append('| 央视（晚高峰救急） | `find_gateway.py` 搜 `newlive/live/hls` → 抠 `host:port` → 验 `#EXTM3U` + 首分片 | `120.40.39.246:352` 本轮接管 6 个央视首选 |')
    L.append('| 卫视长尾 | tsfile 主机 `00NN` 段顺序枚举，用卫视名反查 | `125.93.74.27:9002` 覆盖 16 个卫视 |')
    L.append('| 浙江 / CCTV-1 / CCTV-13 | 浙江卫视官网播放页筛 m3u8 | `ali-m-l.cztv.com` 三条，移动侧 28~50 Mbps |')

    L.append('\n## 四、缺口（无源 / 单点）\n')
    L.append('| 频道 | 现状 | 风险 |')
    L.append('|---|---|---|')
    L.append('| 东方卫视 / 香港卫视 / 广东卫视 | **已从订阅删除**（3 轮全 0，无替补） | 需重新找源才能恢复 |')
    L.append('| CCTV-16 | 仅 `gmxw.7766.org:808/hls/169`，min 2.18 波动大 | 单条无替补 |')
    L.append('| 海南卫视 | 仅 `125.93.74.27:9002` 一条 | 独家单点 |')
    L.append('| 新疆/江西/西藏/广州综合/内蒙古 | 各 1 条 | 单点无备 |')
    L.append('| 湖北本地 7 台 | 长江云 CDN 全 403 | 模板占位 |')

    L.append('\n## 五、机器可读\n')
    L.append('| 文件 | 内容 |')
    L.append('|---|---|')
    L.append('| `iptv/tmp/phone_rates_3r.tsv` | 首选源 3 轮 min/avg/max |')
    L.append('| `iptv/tmp/cand_rates_3r.tsv` | 候选源 3 轮 min/avg/max |')
    L.append('| `iptv/tmp/reorder_report.md` | 本轮换首选 / 删除明细 |')
    L.append('| `iptv/output/curated.txt.bak.20261101` | 重排前的订阅备份 |')
    L.append('\n```bash')
    L.append('python tools/phone_speed.py tmp/primary.txt 3 --sec 4   # 首选 3 轮')
    L.append('python tools/phone_rates_3r.py                          # 解析成 tsv')
    L.append('python tools/reorder_by_phone.py --drop "..."            # 重排+删台')
    L.append('python tools/make_source_table.py && python tools/make_source_html.py')
    L.append('```\n')

    L.append('## 附录 A：每台首选完整地址（%d 条）\n' % len(rows))
    L.append('```')
    for r in rows:
        L.append('%-12s %s' % (r['name'], r['primary_url']))
    L.append('```\n')

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L))

    print('channels=%d hosts=%d rates=%d better=%d'
          % (len(rows), len(hosts), len(rates), len(better)))
    print('md ->', OUT_MD)


if __name__ == '__main__':
    main()
