#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析结果文件的线路构成：每台线路数、host 分布、IP 直连占比、IPv6 占比。

用法: python tools/analyze_result.py [output/user_result.txt]
"""
import re
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else "output/user_result.txt"

CDN_HINT = {
    "mgtv": "芒果TV CDN",
    "hunantv": "芒果系",
    "yangshipin": "央视频",
    "cctv": "央视",
    "migu": "咪咕(移动自有)",
    "bilivideo": "B站",
    "hebtv": "河北广电",
    "nmtv": "内蒙古广电",
    "iqilu": "山东广电",
    "jstv": "江苏广电",
    "kankanews": "上海看看",
    "gdtv": "广东广电",
    "sctv": "四川广电",
    "fjtv": "福建广电",
    "btime": "北京广电",
}


def host_of(url):
    m = re.match(r"^(?:https?|rtmp|rtsp)://([^/]+)", url, re.I)
    return (m.group(1) if m else url).lower()


def main():
    per = defaultdict(list)
    order = []
    cur = None
    ipv6 = ipv4_ip = domain = 0
    for line in open(PATH, encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            if cur not in per:
                order.append(cur)
            continue
        if "," in s and cur:
            name, url = s.split(",", 1)
            url = url.strip()
            if not url.lower().startswith(("http", "rtmp", "rtsp")):
                continue
            per[cur].append((name.strip(), url))
            h = host_of(url)
            if h.startswith("["):
                ipv6 += 1
            elif re.match(r"^\d+\.\d+\.\d+\.\d+", h):
                ipv4_ip += 1
            else:
                domain += 1

    print("线路总数 %d  域名 %d  IPv4直连 %d  IPv6 %d" % (ipv6 + ipv4_ip + domain, domain, ipv4_ip, ipv6))
    print("-" * 58)
    for g in order:
        items = per[g]
        if not items:
            continue
        hosts = Counter(host_of(u).split(":")[0] for _, u in items)
        print("%-8s %2d台 %3d线  top: %s" % (
            g, len({n for n, _ in items}), len(items),
            ", ".join("%s(%d)" % (h[:26], c) for h, c in hosts.most_common(3))))

    print("-" * 58)
    print("CCTV 各台线路数：")
    for g in order:
        for n, u in per[g]:
            if n.startswith("CCTV"):
                pass
    cctv = defaultdict(list)
    for g in order:
        for n, u in per[g]:
            if n.startswith("CCTV"):
                cctv[n].append(host_of(u))
    for k in sorted(cctv, key=lambda s: (len(s), s)):
        hs = Counter(h.split(":")[0] for h in cctv[k])
        print("  %-9s %d 条  %s" % (k, len(cctv[k]), ", ".join(h[:24] for h, _ in hs.most_common(3))))

    print("-" * 58)
    allhosts = Counter()
    for g in order:
        for _, u in per[g]:
            allhosts[host_of(u).split(":")[0]] += 1
    print("全站 top host：")
    for h, c in allhosts.most_common(12):
        tag = next((v for k, v in CDN_HINT.items() if k in h), "")
        print("  %-34s %3d  %s" % (h[:34], c, tag))


if __name__ == "__main__":
    main()
