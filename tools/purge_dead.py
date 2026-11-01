# -*- coding: utf-8 -*-
"""purge_dead.py —— 从 output/curated.txt 剔除指定死机/死链的线路。

用法:
    python tools/purge_dead.py 119.125.131.239:9901 182.114.50.213:9901
    python tools/purge_dead.py --dry 119.125.131.239:9901   # 只看会删多少
"""
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR = os.path.join(ROOT, 'output', 'curated.txt')


def main():
    args = [a for a in sys.argv[1:] if a != '--dry']
    dry = '--dry' in sys.argv
    if not args:
        print(__doc__)
        return
    keep, drop = [], []
    for l in io.open(CUR, encoding='utf-8').read().splitlines():
        if any(h in l for h in args):
            drop.append(l)
        else:
            keep.append(l)
    print("删除 %d 条，保留 %d 条" % (len(drop), len(keep)))
    for d in drop:
        print("  - " + d[:100])
    if dry:
        print("(dry run，未写入)")
        return
    shutil.copy2(CUR, CUR + '.bak.purge')
    with io.open(CUR, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(keep) + '\n')
    print("已写入 %s（备份 %s）" % (CUR, CUR + '.bak.purge'))


if __name__ == '__main__':
    main()
