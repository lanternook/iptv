#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""num_map.py —— 查 IPTV 主机的「台号 → 频道」映射，不要再自己算偏移。

为什么要有这个脚本：txiptv 类主机至少有 3 种编号方案，而且**互不通用**。
历史上两次重大事故都是「按规律硬套编号」造成的：
  - 把 `119.125.131.239` 的 CCTV-6 算成 1020，实际 1020 是 CCTV-5+
  - 把 `101.66.*` 的 0016/0017 当成 CCTV-16/17，实际是北京卫视/江苏卫视
所以：**查表，别算。**

用法:
    python tools/num_map.py                       # 列出已知主机的方案
    python tools/num_map.py 119.125.131.239       # 打印该主机的完整对照表
    python tools/num_map.py 119 6                 # 只查 CCTV-6 对应哪个编号
    python tools/num_map.py 183 CCTV-5+           # 反查：CCTV-5+ 在该主机有没有
    python tools/num_map.py 119 1053              # 反查：1053 是哪个台

输出示例:
    $ python tools/num_map.py 119 6
    119.125.131.239:9901  CCTV-6  ->  1021
"""
import sys

# 方案 A：tsfile 类，绝对编号表（1020 被 CCTV-5+ 占用，6 及以后不对齐）
TSFILE_10NN = {1: 1015, 2: 1016, 3: 1017, 4: 1018, 5: 1019}
TSFILE_10NN[5] = 1019
TSFILE_5PLUS = 1020
TSFILE_6_15 = {n: 1015 + n for n in range(6, 16)}   # 6->1021 ... 15->1030
TSFILE_10NN.update(TSFILE_6_15)

# 方案 B：tsfile 类，00NN（0001~0015=CCTV-1~15，0016=CCTV-17）
TSFILE_00NN = {n: n for n in range(1, 16)}
TSFILE_00NN["17"] = 16

# 卫视（仅 119.125.131.239 这一台已逐帧确认）
WS_119 = {
    "深圳卫视": 1048, "黑龙江卫视": 1049, "北京卫视": 1050, "辽宁卫视": 1051,
    "贵州卫视": 1052, "湖北卫视": 1053, "广西卫视": 1054, "河南卫视": 1055,
    "云南卫视": 1056, "山西卫视": 1057, "安徽卫视": 1059, "四川卫视": 1060,
    "江苏卫视": 1061, "兵团卫视": 1062, "山东卫视": 1063, "重庆卫视": 1066,
    "天津卫视": 1067, "陕西卫视": 1068,
}
# 非卫视（容易误当卫视用）
NOT_WS_119 = {
    1058: "湖南经视", 1064: "河南卫视(重复)", 1065: "北京卫视(重复)",
    1069: "广东经济科教", 1031: "嘉佳卡通", 1032: "卡酷少儿", 1033: "金鹰卡通",
    1034: "优漫卡通", 1035: "南方购物", 1036: "凤凰卫视", 1039: "CETV-1",
    1042: "深圳都市", 1043: "广州影视", 1044: "湖南卫视", 1045: "浙江卫视",
    1046: "江苏卫视", 1047: "东方卫视", 1077: "深圳卫视(梦醒黄金城)", 1078: "岭南戏曲",
}

# newlive 网关类：N 是路径里的数字
GATEWAYS = {
    "183.250.156.180:9999": {
        "scheme": "direct_np",
        "desc": "1~15 直编；16=CCTV-16 奥林匹克（2026-11-01 抓帧，此前是 404）、17=CCTV-17，无 CCTV-5+；29~40 是卫视块",
        "path": "/newlive/live/hls/%d/live.m3u8",
        "cctv_extra": {"CCTV-16": 16},
        "ws": {
            29: "湖南卫视", 30: "江苏卫视", 31: "浙江卫视", 32: "北京卫视",
            33: "广东卫视", 34: "山东卫视", 35: "湖北卫视", 36: "深圳卫视",
            37: "东方卫视", 38: "安徽卫视", 39: "天津卫视", 40: "辽宁卫视",
        },
    },
    "118.122.144.115:8888": {
        "scheme": "direct",
        "desc": "直编，16=CCTV-5+、17=CCTV-17",
        "path": "/newlive/live/hls/%d/live.m3u8",
    },
    "219.147.245.238:25480": {
        "scheme": "shift",
        "desc": "顺移：6=CCTV-5+、7~16=CCTV-6~15、17=CCTV-17，无 CCTV-16",
        "path": "/newlive/live/hls/%d/live.m3u8",
    },
    "61.162.52.6:8088": {
        "scheme": "shift",
        "desc": "顺移同 219.147，CCTV-17 在 18",
        "path": "/newlive/live/hls/%d/live.m3u8",
    },
    "120.40.39.246:352": {
        "scheme": "shift",
        "desc": "顺移同 219.147，但 CCTV-17 在 18",
        "path": "/newlive/live/hls/%d/live.m3u8",
    },
    "119.125.131.239:9901": {
        "scheme": "tsfile",
        "desc": "tsfile 绝对编号表（1020=CCTV-5+），无 CCTV-16/17；2026-11-01 已整机死",
        "path": "/tsfile/live/%04d_1.m3u8?key=txiptv&playlive=1&down=1",
    },
    "58.56.162.102:4466": {
        "scheme": "shift",
        "desc": "顺移，但 6=404（无 CCTV-5+）；7=CCTV-6（已抓帧）；18~32 是卫视块（已逐帧放大核对）",
        "path": "/newlive/live/hls/%d/live.m3u8",
        "no_5plus": True,
        "ws": {
            18: "湖南卫视", 19: "江苏卫视", 20: "北京卫视", 21: "安徽卫视",
            22: "东方卫视", 24: "深圳卫视", 25: "广东卫视", 26: "辽宁卫视",
            28: "东南卫视", 29: "陕西卫视", 30: "海南卫视", 31: "湖北卫视",
            32: "山西卫视",
        },
    },
    "221.226.51.220:50081": {
        "scheme": "direct_np",
        "desc": "1~15 直编（6=CCTV-6、7=CCTV-7 已抓帧），16/17=404，18=江苏卫视",
        "path": "/newlive/live/hls/%d/live.m3u8",
        "no17": True,
        "ws": {18: "江苏卫视"},
    },
    "113.57.140.161:10081": {
        "scheme": "direct_np",
        "desc": "1~15 直编；16 起是混合频道列表（16=广东卫视、17=浙江卫视、22=北京、24=天津），无 CCTV-5+",
        "path": "/newlive/live/hls/%d/live.m3u8",
        "no17": True,
        "ws": {16: "广东卫视", 17: "浙江卫视", 22: "北京卫视", 24: "天津卫视"},
    },
}


def resolve_gateway(key):
    """按前缀/包含匹配主机名（优先前缀命中，避免 '61' 命中 '113...161'）。"""
    if key in GATEWAYS:
        return key
    hits = [h for h in GATEWAYS if h.startswith(key)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        hits = [h for h in GATEWAYS if key in h]
    return hits[0] if len(hits) == 1 else None


def cctv_to_num(host, ch):
    """CCTV 频道 -> 该主机的路径数字。ch 形如 '6' / 'CCTV-6' / '5+'。"""
    s = str(ch).replace("CCTV-", "").replace("cctv", "").strip()
    # 个别主机有「例外台」：如 183 的 CCTV-16 在 N=16
    for k, v in (GATEWAYS[host].get("cctv_extra") or {}).items():
        if k.replace("CCTV-", "") == s:
            return v
    scheme = GATEWAYS[host]["scheme"]
    if s in ("5+", "5plus", "5PLUS"):
        if GATEWAYS[host].get("no_5plus"):
            return None
        if scheme == "direct":
            return 16
        if scheme in ("shift", "tsfile"):
            return 1020 if scheme == "tsfile" else 6
        return None
    if not s.isdigit():
        return None
    n = int(s)
    if scheme == "tsfile":
        return TSFILE_10NN.get(n)
    if scheme == "direct":
        # 1~15 直通；16 被 CCTV-5+ 占了；17 = CCTV-17
        if n == 16:
            return None
        return n
    if scheme == "direct_np":
        # 1~15 直通；16 = 404（没有 5+）；17 可能 404（221/113 实测 404）
        if n == 16:
            return None
        if n == 17 and GATEWAYS[host].get("no17"):
            return None
        return n
    if scheme == "shift":
        # 5=5、6=5+、N>=7 是 CCTV-(N-1)；CCTV-17 有的机在 17 有的在 18
        if n == 5:
            return 5
        if n == 17:
            return 18 if host in ("61.162.52.6:8088", "120.40.39.246:352") else 17
        if n == 16:
            return None
        return n + 1 if n >= 6 else n
    return None


def num_to_cctv(host, num):
    for n in list(range(1, 18)) + ["5+"]:
        if cctv_to_num(host, n) == num:
            return "CCTV-%s" % n
    return None


def print_table(host):
    v = GATEWAYS[host]
    print("%s  [%s]  %s" % (host, v["scheme"], v["desc"]))
    print("路径模板：http://%s%s" % (host, v["path"]))
    print()
    if v["scheme"] == "tsfile":
        print("央视：")
        row = []
        for n in list(range(1, 6)) + ["5+"] + list(range(6, 16)):
            num = cctv_to_num(host, n)
            row.append("CCTV-%-3s → %s" % (n, num if num else "无"))
        for i in range(0, len(row), 4):
            print("  " + "   ".join(row[i:i + 4]))
        print("\n卫视：")
        row = ["%s → %d" % (k, v2) for k, v2 in WS_119.items()]
        for i in range(0, len(row), 3):
            print("  " + "   ".join(row[i:i + 3]))
        print("\n非卫视（别当卫视用）：")
        row = ["%d=%s" % (k, v2) for k, v2 in NOT_WS_119.items()]
        for i in range(0, len(row), 3):
            print("  " + "   ".join(row[i:i + 3]))
    else:
        print("央视：")
        row = []
        for n in list(range(1, 17)) + ["5+", 17]:
            num = cctv_to_num(host, n)
            row.append("CCTV-%-3s → %s" % (n, num if num else "无"))
        for i in range(0, len(row), 4):
            print("  " + "   ".join(row[i:i + 4]))
        print("\n注意：卫视编号未验证，必须抓帧。")
    print("\n⚠ 该主机是否存活需另测：python tools/speed_multi.py 清单.txt 1 --by-url")


def main():
    if len(sys.argv) == 1:
        print("已知主机（台号方案互不通用，别互相套）：\n")
        for h, v in GATEWAYS.items():
            print("  %-24s %-10s %s" % (h, v["scheme"], v["desc"]))
        print("\n用法：")
        print("  python tools/num_map.py 119              # 前缀匹配，打印全表")
        print("  python tools/num_map.py 119 6            # CCTV-6 → 编号")
        print("  python tools/num_map.py 119 CCTV-5+      # 反查")
        print("  python tools/num_map.py 119 1053         # 编号 → 台名")
        return 0

    host = resolve_gateway(sys.argv[1])
    if not host:
        print("未收录该主机：%s" % sys.argv[1])
        print("已收录：" + ", ".join(GATEWAYS))
        return 1

    if len(sys.argv) == 2:
        print_table(host)
        return 0

    arg = sys.argv[2]
    # 反查：纯数字且 >= 1000，或数字在卫视表里
    if arg.isdigit():
        n = int(arg)
        if n >= 1000:
            name = num_to_cctv(host, n)
            if not name:
                for k, v in WS_119.items():
                    if v == n:
                        name = k
                        break
            if not name:
                name = NOT_WS_119.get(n, "未知")
            print("%s  %d  ->  %s" % (host, n, name))
            return 0
    num = cctv_to_num(host, arg)
    if num is None:
        print("%s  CCTV-%s  ->  该主机没有这个台" % (host, str(arg).replace("CCTV-", "")))
        return 2
    print("%s  CCTV-%s  ->  %d" % (host, str(arg).replace("CCTV-", ""), num))
    return 0


if __name__ == "__main__":
    sys.exit(main())
