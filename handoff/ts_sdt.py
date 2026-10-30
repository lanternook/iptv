#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ts_sdt.py —— 从 HLS 流里解析出频道名（读 TS 的 SDT 表，PID 0x11 / table_id 0x42）。

用途：IPTV 转 HLS 网关的频道号（如 .../hls/12/live.m3u8）不含台名，
只能从码流的 service_descriptor 里读。用于批量识别枚举出来的频道号。

用法:
    python tools/ts_sdt.py http://120.40.39.246:352/newlive/live/hls/1/live.m3u8
    python tools/ts_sdt.py --tpl "http://120.40.39.246:352/newlive/live/hls/{n}/live.m3u8" --from 1 --to 36
"""
import argparse
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, max_bytes=400_000, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with OP.open(req, timeout=timeout) as r:
        return r.read(max_bytes)


def first_segment(m3u8_text, base):
    lines = [l.strip() for l in m3u8_text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    return urllib.parse.urljoin(base, nxt)
    for line in lines:
        if not line.startswith("#"):
            return urllib.parse.urljoin(base, line)
    return None


def parse_sdt(payload):
    """payload 为 SDT section 起始（table_id 已读或未读，这里传入从 table_id 开始的数据）。"""
    if len(payload) < 11 or payload[0] != 0x42:
        return []
    section_length = ((payload[1] & 0x0F) << 8) | payload[2]
    end = min(3 + section_length - 4, len(payload))  # 去掉 CRC32
    pos = 11  # table_id(1)+len(2)+tsid(2)+ver(1)+sec(1)+last(1)+onid(2)+reserved(1)
    names = []
    while pos + 5 <= end:
        service_id = (payload[pos] << 8) | payload[pos + 1]
        loop_len = ((payload[pos + 3] & 0x0F) << 8) | payload[pos + 4]
        pos += 5
        d_end = min(pos + loop_len, end)
        while pos + 2 <= d_end:
            tag, dlen = payload[pos], payload[pos + 1]
            body = payload[pos + 2: pos + 2 + dlen]
            if tag == 0x48 and len(body) >= 3:
                p_len = body[1]
                s_off = 2 + p_len
                if s_off < len(body):
                    s_len = body[s_off]
                    raw = body[s_off + 1: s_off + 1 + s_len]
                    name = decode_dvb(raw)
                    if name:
                        names.append((service_id, name))
            pos += 2 + dlen
        pos = d_end
    return names


def decode_dvb(raw):
    if not raw:
        return ""
    enc = "utf-8"
    if raw[0] < 0x20:  # DVB 字符表选择字节
        sel = raw[0]
        raw = raw[1:]
        if sel < 0x10:
            enc = "latin-1"
        elif sel >= 0x15:
            enc = "utf-8"
    for e in (enc, "gbk", "utf-8", "latin-1"):
        try:
            s = raw.decode(e, "strict").strip("\x00").strip()
            if s and s.isprintable():
                return s
        except Exception:  # noqa: BLE001
            continue
    return raw.decode("gbk", "replace").strip("\x00").strip()


def channel_name(m3u8_url):
    text = fetch(m3u8_url, max_bytes=65536).decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        return None, "非 m3u8"
    seg = first_segment(text, m3u8_url)
    if not seg:
        return None, "无分片"
    data = fetch(seg, max_bytes=400_000)
    if not data or data[0] != 0x47:
        return None, "非 TS 流（可能 fMP4）"
    # 逐包扫描，找 PID=0x11 且 PUSI=1 的 SDT
    for off in range(0, len(data) - 188, 188):
        if data[off] != 0x47:
            continue
        pid = ((data[off + 1] & 0x1F) << 8) | data[off + 2]
        if pid != 0x11:
            continue
        pusi = data[off + 1] & 0x40
        if not pusi:
            continue
        afc = (data[off + 3] >> 4) & 0x03
        p = off + 4
        if afc & 0x02:
            p += 1 + data[p]
        if p >= off + 188:
            continue
        ptr = data[p]
        body = data[p + 1 + ptr: off + 188]
        names = parse_sdt(body)
        if names:
            return " / ".join(n for _, n in names), "SDT"
    return None, "未找到 SDT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--tpl", default=None)
    ap.add_argument("--from", dest="lo", type=int, default=1)
    ap.add_argument("--to", dest="hi", type=int, default=36)
    a = ap.parse_args()

    if a.tpl:
        for n in range(a.lo, a.hi + 1):
            u = a.tpl.format(n=n)
            try:
                name, how = channel_name(u)
            except (urllib.error.URLError, socket.timeout, OSError) as e:
                name, how = None, type(e).__name__
            print("%-4d %-28s %s" % (n, name or "(未知)", how))
        return 0

    if not a.url:
        sys.exit(__doc__)
    name, how = channel_name(a.url)
    print("%s  ->  %s  [%s]" % (a.url, name or "(未知)", how))
    return 0


if __name__ == "__main__":
    sys.exit(main())
