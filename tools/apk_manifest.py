# -*- coding: utf-8 -*-
"""下载央视频TV官方 APK 并解析 AndroidManifest 的 minSdk/targetSdk/权限。

不依赖 aapt / androguard，自己解二进制 AXML。
用法：python tools/apk_manifest.py <apk_url|本地路径>
"""
import io
import os
import re
import struct
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(BASE, 'tmp')

# ---- AXML 常量 ----
RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102
RES_XML_RESOURCE_MAP = 0x0180
ATTR_MIN_SDK = 0x0101020c
ATTR_TARGET_SDK = 0x01010270
ATTR_NAME = 0x01010003
ATTR_VERSION_NAME = 0x0101021b
ATTR_VERSION_CODE = 0x0101021c
ATTR_PERMISSION = 0x01010006


def read_string_pool(buf, off):
    _, hsz, size = struct.unpack_from('<HHI', buf, off)
    cnt, _, flags, sstart, _ = struct.unpack_from('<IIIII', buf, off + 8)
    utf8 = bool(flags & 0x100)
    offs = struct.unpack_from('<%dI' % cnt, buf, off + hsz)
    base = off + sstart
    out = []
    for o in offs:
        p = base + o
        try:
            if utf8:
                # utf16len(变长) + utf8len(变长) + bytes + 0
                n = buf[p]
                p += 2 if n & 0x80 else 1
                n = buf[p]
                if n & 0x80:
                    n = ((n & 0x7f) << 8) | buf[p + 1]
                    p += 2
                else:
                    p += 1
                out.append(buf[p:p + n].decode('utf-8', 'replace'))
            else:
                n = struct.unpack_from('<H', buf, p)[0]
                p += 2
                if n & 0x8000:
                    n = ((n & 0x7fff) << 16) | struct.unpack_from('<H', buf, p)[0]
                    p += 2
                out.append(buf[p:p + n * 2].decode('utf-16-le', 'replace'))
        except Exception:  # noqa: BLE001
            out.append('')
    return out


def parse_axml(buf):
    _, _, total = struct.unpack_from('<HHI', buf, 0)
    pos = 8
    strings, resmap = [], []
    elements = []
    while pos < min(total, len(buf)):
        ctype, hsz, csize = struct.unpack_from('<HHI', buf, pos)
        if csize <= 0:
            break
        if ctype == RES_STRING_POOL:
            strings = read_string_pool(buf, pos)
        elif ctype == RES_XML_RESOURCE_MAP:
            n = (csize - hsz) // 4
            resmap = list(struct.unpack_from('<%dI' % n, buf, pos + hsz))
        elif ctype == RES_XML_START_ELEMENT:
            name_idx, acount = struct.unpack_from('<II', buf, pos + 20)[0], None
            name_idx = struct.unpack_from('<I', buf, pos + 20)[0]
            acount, _ = struct.unpack_from('<HH', buf, pos + 28)
            apos = pos + hsz
            attrs = {}
            for _ in range(acount):
                ns_i, nm_i, raw_i, _, _, dtype, data = struct.unpack_from('<IIIHBBI', buf, apos)
                key = strings[nm_i] if nm_i < len(strings) else ''
                rid = resmap[nm_i] if nm_i < len(resmap) else 0
                if dtype == 0x03:      # string
                    val = strings[data] if data < len(strings) else ''
                elif dtype == 0x12:    # int
                    val = data
                elif dtype == 0x10:
                    val = data
                else:
                    val = data
                attrs[(key, rid)] = val
                apos += 20
            elements.append((strings[name_idx] if name_idx < len(strings) else '', attrs))
        pos += csize
    return elements


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else ''
    local = os.path.join(TMP, os.path.basename(src) or 'app.apk')
    if src.startswith('http'):
        if not os.path.exists(local) or os.path.getsize(local) < 1000000:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            op.addheaders = [('User-Agent', 'Mozilla/5.0')]
            print('下载', src)
            with op.open(src, timeout=180) as r, io.open(local, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
    print('apk', local, os.path.getsize(local), 'bytes')

    import zipfile
    with zipfile.ZipFile(local) as z:
        names = z.namelist()
        ax = z.read('AndroidManifest.xml')
    els = parse_axml(ax)

    info = {'pkg': '', 'minSdk': None, 'targetSdk': None, 'verName': '',
            'verCode': None, 'perms': [], 'activities': 0, 'has_live': False}
    for tag, at in els:
        if tag == 'manifest':
            info['pkg'] = at.get(('package', 0), '')
            info['verName'] = at.get(('versionName', ATTR_VERSION_NAME), '')
            info['verCode'] = at.get(('versionCode', ATTR_VERSION_CODE), '')
        elif tag == 'uses-sdk':
            info['minSdk'] = at.get(('minSdkVersion', ATTR_MIN_SDK))
            info['targetSdk'] = at.get(('targetSdkVersion', ATTR_TARGET_SDK))
        elif tag == 'uses-permission':
            p = at.get(('name', ATTR_PERMISSION)) or at.get(('name', ATTR_NAME))
            if p:
                info['perms'].append(p)
        elif tag == 'activity':
            info['activities'] += 1

    # 粗略判断是否含直播相关能力
    blob = ' '.join(n.lower() for n in names)
    info['has_live'] = any(k in blob for k in ('live', 'tv', 'player'))
    info['libs'] = sorted({n.split('/')[1] for n in names
                           if n.startswith('lib/') and n.count('/') > 1})[:8]
    info['dex'] = [n for n in names if n.endswith('.dex')]

    print('package   ', info['pkg'])
    print('versionName', info['verName'], 'verCode', info['verCode'])
    print('minSdk    ', info['minSdk'], ' targetSdk', info['targetSdk'])
    print('activities', info['activities'])
    print('libs      ', info['libs'])
    print('dex       ', info['dex'])
    print('perms     ', len(info['perms']), '条:',
          [p for p in info['perms'] if 'INTERNET' in p or 'NETWORK' in p])
    print('so/abi 命中 live:', info['has_live'])


if __name__ == '__main__':
    main()
