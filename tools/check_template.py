#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验频道模板（user_demo.txt）格式，规则与 iptv-api 的 demo_txt_pattern 一致。

用法: python tools/check_template.py [config/user_demo.txt]
"""
import re
import sys

# 与 utils/constants.py 一致：名称不含中英文逗号，可选逗号+值
PAT = re.compile(r"^(?P<name>[^,，]+)[,，]?(?!#genre#)(?P<value>.+)?$")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "config/user_demo.txt"
    groups, cur, problems = {}, None, []
    seen = {}
    with open(path, encoding="utf-8") as f:
        for i, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            if "#genre#" in line:
                cur = re.split(r"[，,]", line, maxsplit=1)[0].strip()
                if cur in groups:
                    problems.append("第%d行: 分组重复 %s" % (i, cur))
                groups[cur] = []
                continue
            if cur is None:
                problems.append("第%d行: 出现在任何分组之前 -> %s" % (i, line))
                continue
            m = PAT.match(line)
            if not m:
                problems.append("第%d行: 无法解析 -> %s" % (i, line))
                continue
            name, value = m.group("name").strip(), (m.group("value") or "").strip()
            if name.startswith("#"):
                problems.append("第%d行: 注释行会被当成频道名 -> %s" % (i, line))
            if name in seen and seen[name] != cur:
                problems.append("第%d行: 频道名跨分组重复 %s（前一次在 %s）" % (i, name, seen[name]))
            seen[name] = cur
            groups[cur].append((name, value))

    total = 0
    for g, items in groups.items():
        print("%-12s %3d 个频道  (含直链 %d)" % (g, len(items), sum(1 for _, v in items if v)))
        total += len(items)
    print("-" * 40)
    print("分组 %d 个，频道 %d 个" % (len(groups), total))
    if problems:
        print("\n发现问题:")
        for p in problems:
            print("  " + p)
        return 1
    print("格式校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
