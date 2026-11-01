# -*- coding: utf-8 -*-
"""fill_gateways.py —— 按 num_map 的编号表，把指定网关的线路补进 curated.txt。

编号**全部查 num_map.cctv_to_num()**，本脚本不自己算偏移。

用法:
    python tools/fill_gateways.py 58.56 61.162 221.226 113.57
    python tools/fill_gateways.py --dry 58.56
    python tools/fill_gateways.py --ws-only 221.226     # 只补卫视，不补央视
"""
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import num_map as NM  # noqa: E402

CUR = os.path.join(ROOT, 'output', 'curated.txt')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry' in sys.argv
    ws_only = '--ws-only' in sys.argv
    if not args:
        print(__doc__)
        return 1

    lines = io.open(CUR, encoding='utf-8').read().splitlines()
    channels, order = set(), []
    for l in lines:
        s = l.strip()
        if s and ',' in s and not s.startswith('#'):
            n = s.split(',', 1)[0].strip()
            if n not in channels:
                channels.add(n)
                order.append(n)

    added = []
    for key in args:
        host = NM.resolve_gateway(key)
        if not host:
            print("跳过（未收录）：%s" % key)
            continue
        info = NM.GATEWAYS[host]
        tpl = info['path']
        base = 'http://' + host
        if not ws_only:
            for ch in order:
                if not ch.startswith('CCTV'):
                    continue
                num = NM.cctv_to_num(host, ch.replace('CCTV-', ''))
                if num is None:
                    continue
                url = base + (tpl % num)
                added.append((ch, url, False))
        for num, name in (info.get('ws') or {}).items():
            url = base + (tpl % num)
            added.append((name, url, True))

    exist = set(l.strip() for l in lines)
    new = []
    for ch, url, is_ws in added:
        line = '%s,%s' % (ch, url)
        if line in exist:
            continue
        if ch not in channels and not is_ws:
            continue
        exist.add(line)
        new.append(line)

    print("新增 %d 条" % len(new))
    for l in new:
        print("  + " + l)
    if dry or not new:
        return 0

    shutil.copy2(CUR, CUR + '.bak.fill')
    # 按台插到该台最后一条之后，保持分组
    out = list(lines)
    for l in new:
        ch = l.split(',', 1)[0]
        idx = None
        for i, x in enumerate(out):
            if x.strip().startswith(ch + ','):
                idx = i
        if idx is None:
            out.append(l)
        else:
            out.insert(idx + 1, l)
    with io.open(CUR, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print("已写入 %s（备份 .bak.fill）" % CUR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
