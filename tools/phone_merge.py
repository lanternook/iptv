# -*- coding: utf-8 -*-
"""phone_merge.py —— 合并多轮手机测速结果，按「手机(目标机同网)」数据重排 curated.txt。

为什么不用 apply_phone_speed.py：那个脚本一次只吃一组 list/result，
而实际会分批测（老线路一批、新补线路一批），分两次跑会把没送测的线路误判成死链沉底。

用法:
    python tools/phone_merge.py --pairs tmp/_phone_all.txt:output/phone_result_r1.txt \
                                --pairs tmp/_phone_new.txt:output/phone_result_r2.txt
    python tools/phone_merge.py ... --dry
    python tools/phone_merge.py ... --purge 0.8     # 顺带删掉手机侧 <0.8 Mbps 的死链

排序键：可用(200 且 >100KB) 优先 → Mbps 降序 → 原始顺序。
"""
import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CUR = os.path.join(ROOT, 'output', 'curated.txt')


def load_pair(list_path, res_path):
    """返回 {url: (alive, mbps)}"""
    tag2url = {}
    for raw in io.open(list_path, encoding='utf-8', errors='replace'):
        s = raw.strip()
        if '|' in s:
            t, u = s.split('|', 1)
            tag2url[t.strip()] = u.strip()
    out = {}
    for raw in io.open(res_path, encoding='utf-8', errors='replace'):
        p = raw.strip().split('|')
        if len(p) < 4:
            continue
        tag = p[0].strip()
        try:
            mb = float(p[1])
        except ValueError:
            mb = 0.0
        code = p[2].strip()
        try:
            nbytes = int(float(p[3])) if p[3] != 'm3u8fail' else 0
        except ValueError:
            nbytes = 0
        u = tag2url.get(tag)
        if not u:
            continue
        alive = (code == '200' and mb > 0 and nbytes >= 100000)
        # 同一 URL 多轮：取 min（防假快），alive 要求至少一轮可用
        if u in out:
            pa, pm = out[u]
            out[u] = (pa or alive, min(pm, mb))
        else:
            out[u] = (alive, mb)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pairs', action='append', required=True)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--purge', type=float, default=None)
    ap.add_argument('--cap-cctv', type=int, default=5)
    ap.add_argument('--cap-ws', type=int, default=4)
    a = ap.parse_args()

    stat = {}
    for pair in a.pairs:
        lp, rp = pair.split(':')
        d = load_pair(lp, rp)
        for u, v in d.items():
            if u in stat:
                pa, pm = stat[u]
                stat[u] = (pa or v[0], min(pm, v[1]))
            else:
                stat[u] = v
    print("测速覆盖 %d 条 URL" % len(stat))

    lines = io.open(CUR, encoding='utf-8').read().splitlines()
    out = []
    section = None
    block_name = None
    block_urls = []
    dropped = []

    def flush():
        nonlocal block_name, block_urls
        if block_name is None:
            return
        scored = []
        for i, u in enumerate(block_urls):
            alive, mb = stat.get(u, (False, 0.0))
            scored.append((0 if alive else 1, -mb, i, u, mb, alive))
        scored.sort()
        cap = a.cap_cctv if block_name.startswith('CCTV') else a.cap_ws
        kept = 0
        for k, (_, _, _, u, mb, alive) in enumerate(scored):
            if a.purge is not None and not alive and mb < a.purge:
                dropped.append((block_name, u, mb))
                continue
            if kept >= cap:
                dropped.append((block_name, u, mb))
                continue
            kept += 1
            out.append('%s,%s' % (block_name, u))
        block_name = None
        block_urls = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.endswith(',#genre#'):
            flush()
            out.append(s)
            section = s.split(',')[0]
            continue
        if ',' not in s:
            continue
        n, u = s.split(',', 1)
        n, u = n.strip(), u.strip()
        if block_name is not None and n != block_name:
            flush()
        if block_name is None:
            block_name = n
        block_urls.append(u)
    flush()

    print("输出 %d 行，删除死链 %d 条" % (len(out), len(dropped)))
    for n, u, mb in dropped:
        print("  - [%.2f] %s %s" % (mb, n, u[:80]))

    if a.dry:
        return 0
    shutil.copy2(CUR, CUR + '.bak.merge')
    with io.open(CUR, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print("已写入 %s" % CUR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
