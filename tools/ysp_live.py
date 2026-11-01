# -*- coding: utf-8 -*-
"""央视频直播地址获取（cKey 签名版）+ 流的加密检测。

算法来源：public real-url/yangshipin.py
  ckey = "--01" + HEX(AES-128-CBC(key, iv, pkcs7(xu))).upper()
  xu   = "|" + int32(fnv-ish(wu)) + wu
  wu   = "|vid|tt|jc|ver|guid|platform|referer|ua"
接口：GET https://liveinfo.yangshipin.cn/  ->  {"playurl": "..."}

只做三件事：拿地址 → 看是不是标准 m3u8 → 看有没有 EXT-X-KEY。
"""
import binascii
import ctypes
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import uuid

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')
os.makedirs(TMP, exist_ok=True)

KEY = binascii.a2b_hex('4E2918885FD98109869D14E0231A0BF4')
IV = binascii.a2b_hex('16B17E519DDD0CE5B79D7A63A4DD801C')
JC = 'mg3c3b04ba'
VER = '3.0.37'
GUID = 'ko7djb70_vbjvrg5gcm'
PLATFORM = 4330701
UA_M = ('Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 '
        'Mobile/15E148 Safari/604.1')
REF = 'https://m.yangshipin.cn/'

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ssl._create_default_https_context = ssl._create_unverified_context


def _aes_cbc_pure(text: bytes) -> bytes:
    """纯标准库 AES-128-CBC 加密（无 pycryptodome 时用）。"""
    try:
        from Crypto.Cipher import AES  # noqa: PLC0415
        pad = 16 - len(text) % 16
        t = text + bytes([pad]) * pad
        return AES.new(KEY, AES.MODE_CBC, IV).encrypt(t)
    except ImportError:
        pass
    # ---- 最小 AES-128 实现 ----
    sbox = [
        0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
        0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
        0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
        0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
        0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
        0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
        0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
        0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
        0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
        0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
        0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
        0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
        0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
        0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
        0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
        0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
    ]
    rcon = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]

    def xt(a):
        return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else a << 1

    def mul(a, b):
        p = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            a = xt(a)
            b >>= 1
        return p

    def expand(k):
        w = [list(k[i:i + 4]) for i in range(0, 16, 4)]
        for i in range(4, 44):
            t = list(w[i - 1])
            if i % 4 == 0:
                t = t[1:] + t[:1]
                t = [sbox[b] for b in t]
                t[0] ^= rcon[i // 4 - 1]
            w.append([w[i - 4][j] ^ t[j] for j in range(4)])
        return w

    def enc_block(blk, w):
        s = [blk[i] ^ w[i // 4][i % 4] for i in range(16)]
        for rnd in range(1, 11):
            s = [sbox[b] for b in s]
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows
            if rnd != 10:
                n = []
                for c in range(4):
                    a = s[c * 4:c * 4 + 4]
                    n += [mul(a[0], 2) ^ mul(a[1], 3) ^ a[2] ^ a[3],
                          a[0] ^ mul(a[1], 2) ^ mul(a[2], 3) ^ a[3],
                          a[0] ^ a[1] ^ mul(a[2], 2) ^ mul(a[3], 3),
                          mul(a[0], 3) ^ a[1] ^ a[2] ^ mul(a[3], 2)]
                s = n
            s = [s[i] ^ w[rnd * 4 + i // 4][i % 4] for i in range(16)]
        return s

    pad = 16 - len(text) % 16
    data = text + bytes([pad]) * pad
    w = expand(KEY)
    out, prev = b'', IV
    for i in range(0, len(data), 16):
        blk = [data[i + j] ^ prev[j] for j in range(16)]
        e = bytes(enc_block(blk, w))
        out += e
        prev = e
    return out


def make_ckey(vid, tt):
    """wu 里的 UA 段是**固定模板串**，不是真实 UA。
    参考实现硬编码为 'mozilla/5.0 (iphone; cpu||Mozilla|Netscape|Win32| '，
    用真实 UA 拼会导致服务端校验失败（返回 iretcode 32）。"""
    wu = ('|%s|%d|%s|%s|%s|%d|%s|mozilla/5.0 (iphone; cpu||Mozilla|Netscape|Win32| '
          % (vid, tt, JC, VER, GUID, PLATFORM, REF))
    u = 0
    for ch in wu:
        u = (u << 5) - u + ord(ch)
        u &= 0xffffffff
    bu = ctypes.c_int32(u).value
    xu = ('|%d%s' % (bu, wu)).encode('utf-8')
    return '--01' + binascii.b2a_hex(_aes_cbc_pure(xu)).decode().upper()


def get_live_url(vid, pid):
    tt = int(time.time())
    params = {
        'cmd': 2, 'cnlid': vid, 'pla': 0, 'stream': 2, 'system': 1,
        'appVer': VER, 'encryptVer': '8.1', 'qq': 0, 'device': 'PC',
        'guid': GUID, 'defn': 'auto', 'host': 'yangshipin.cn',
        'livepid': pid, 'logintype': 1, 'vip_status': 1, 'livequeue': 1,
        'fntick': tt, 'tm': tt, 'sdtfrom': 113, 'platform': PLATFORM,
        'cKey': make_ckey(vid, tt), 'queueStatus': 0, 'uhd_flag': 4,
        'flowid': uuid.uuid4().hex, 'sphttps': 1,
        'callback': 'txvlive_videoinfoget_%d' % tt,
    }
    url = 'https://liveinfo.yangshipin.cn/?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': UA_M, 'Referer': REF, 'Cookie': 'guid=%s' % GUID,
        'Accept': '*/*',
    })
    try:
        r = op.open(req, timeout=20)
        raw = r.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return {'error': str(e), 'request': url[:200]}
    # JSONP 包裹
    m = re.search(r'\{.*\}', raw, re.S)
    j = {}
    if m:
        try:
            j = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            pass
    return {'code': r.status, 'raw': raw[:600], 'json': j,
            'playurl': j.get('playurl', '')}


def inspect_stream(u):
    if not u:
        return {'skip': True}
    req = urllib.request.Request(u, headers={
        'User-Agent': UA_M, 'Referer': REF, 'Accept': '*/*'})
    try:
        r = op.open(req, timeout=15)
        b = r.read(200000)
        ct = r.headers.get('Content-Type', '')
    except Exception as e:  # noqa: BLE001
        return {'error': str(e)}
    t = b.decode('utf-8', 'replace')
    return {
        'ct': ct, 'bytes': len(b), 'm3u8': '#EXTM3U' in t,
        'keys': re.findall(r'#EXT-X-KEY:([^\n]+)', t)[:2],
        'variant': re.findall(r'^(?!#)(\S+\.m3u8\S*)$', t, re.M)[:3],
        'seg': re.findall(r'^(?!#)(\S+\.(?:ts|m4s)\S*)$', t, re.M)[:2],
        'head': t[:300],
    }


if __name__ == '__main__':
    VID = sys.argv[1] if len(sys.argv) > 1 else '2000210103'
    PID = sys.argv[2] if len(sys.argv) > 2 else '600001859'
    print('vid=%s pid=%s' % (VID, PID))
    print('cKey =', make_ckey(VID, int(time.time())))
    res = get_live_url(VID, PID)
    res['stream'] = inspect_stream(res.get('playurl', ''))
    with io.open(os.path.join(TMP, 'ysp_live.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print('code', res.get('code'), 'playurl', (res.get('playurl') or '')[:160])
    if not res.get('playurl'):
        print('raw:', res.get('raw', res.get('error', ''))[:400])
    st = res['stream']
    if st.get('m3u8'):
        print('stream: m3u8=True enc=%s' % bool(st['keys']))
        if st['keys']:
            print('  KEY:', st['keys'][0][:150])
        if st['variant']:
            print('  VAR:', st['variant'][0][:110])
        if st['seg']:
            print('  SEG:', st['seg'][0][:110])
    elif not st.get('skip'):
        print('stream:', st.get('ct'), st.get('bytes'), str(st.get('head', ''))[:120])
    print('-> tmp/ysp_live.json')
