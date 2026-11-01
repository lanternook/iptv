# -*- coding: utf-8 -*-
"""查询 IPTV 源主机归属，结果落盘 tmp/ip_owner.tsv（纯标准库）"""
import sys, io, os, json, urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

IPS = """119.125.131.239 125.93.74.27 218.13.170.98 153.0.171.163 119.39.9.8
112.27.5.218 218.84.12.186 183.250.156.180 118.122.144.115 219.147.245.238
120.40.39.246 61.162.52.6 58.56.162.102 219.147.200.6 221.226.51.220
222.240.44.42 113.57.140.161""".split()

PROXY = "http://127.0.0.1:7897"


def fetch(ip, use_proxy):
    url = ("http://ip-api.com/json/%s?lang=zh-CN"
           "&fields=status,country,regionName,city,isp" % ip)
    if use_proxy:
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(url, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


out = []
for ip in IPS:
    row = [ip, "", "", "", ""]
    for use_proxy in (False, True):
        try:
            d = fetch(ip, use_proxy)
            if d.get("status") == "success":
                row = [ip, d.get("country", ""), d.get("regionName", ""),
                       d.get("city", ""), d.get("isp", "")]
                break
        except Exception as e:
            row[1] = "ERR:%s" % type(e).__name__
    out.append(row)
    print("\t".join(row))

os.makedirs("tmp", exist_ok=True)
with open("tmp/ip_owner.tsv", "w", encoding="utf-8", newline="") as f:
    for r in out:
        f.write("\t".join(r) + "\n")
print("saved tmp/ip_owner.tsv")
