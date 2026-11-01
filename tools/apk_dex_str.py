#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 APK 的 dex 里挖 OTT 取流线索（纯标准库，不依赖 androguard）。

思路：dex 的 string_ids 区是一张纯字符串表，把所有字符串抽出来，
再按关键字过滤。比反编译轻，但足够定位域名/接口路径。

关注：
  - 域名：yangshipin / newtv / cntv / cctv / ott
  - 接口路径：live / playinfo / get_live / channel / m3u8
  - 鉴权：license / token / sign / appid / secret
"""
import re
import sys
import zipfile

APK = 'tmp/cctv.xst-newtv-release-7.2.0.apk'

# dex 里字符串表是 MUTF-8，长度前缀是 ULEB128。
# 粗暴但有效的办法：直接在字节流里找可打印 ASCII 串。
PRINTABLE = re.compile(rb'[ -~]{6,200}')

DOMAIN = re.compile(
    rb'(?:https?://)?(?:[a-z0-9-]+\.)+'
    rb'(?:yangshipin|newtv|cntv|cctv|cctvcom|myqcloud|alicdn|'
    rb'wscdns|bdydns|myhwcdn|kcdnvip|chinamobile|10086|wasu|'
    rb'cibn|wasumedia|sctv|migu)\.[a-z]{2,6}')
PATHY = re.compile(rb'/(?:api|v\d|live|play|ott|channel)[/\w.{}%-]{3,90}')


def dex_strings(blob):
    """从 dex 字节流抽可打印串（粗粒度，够用）。"""
    return [m.group(0).decode('latin-1') for m in PRINTABLE.finditer(blob)]


def main():
    z = zipfile.ZipFile(APK)
    dexes = [n for n in z.namelist() if n.endswith('.dex')]
    print('dex 文件: %s' % dexes)

    allstr = []
    for n in dexes:
        blob = z.read(n)
        ss = dex_strings(blob)
        allstr.extend(ss)
        print('  %s -> %d 串' % (n, len(ss)))

    uniq = sorted(set(allstr))
    print('去重后 %d 串' % len(uniq))

    # 1) 域名
    doms = set()
    for s in uniq:
        for m in DOMAIN.finditer(s.encode('latin-1', 'ignore')):
            doms.add(m.group(0).decode('latin-1'))
    print('\n=== 相关域名 %d 个 ===' % len(doms))
    for d in sorted(doms):
        print('  ' + d)

    # 2) 接口路径
    paths = set()
    for s in uniq:
        for m in PATHY.finditer(s.encode('latin-1', 'ignore')):
            paths.add(m.group(0).decode('latin-1'))
    print('\n=== 疑似接口路径 %d 个（取前 80）===' % len(paths))
    for p in sorted(paths)[:80]:
        print('  ' + p)

    # 3) 鉴权关键字命中
    kw = ['license', 'appid', 'appsecret', 'secret', 'sign=', 'token',
          'playinfo', 'getlive', 'get_live', 'liveurl', 'playurl',
          'm3u8', 'flv', 'widevine', 'drm']
    print('\n=== 关键字命中 ===')
    for k in kw:
        hits = [s for s in uniq if k in s.lower()]
        print('  %-10s %d 条' % (k, len(hits)))
        for h in hits[:6]:
            print('      ' + h[:110])

    with open('tmp/apk_dex_str.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(uniq))
    print('\n全部字符串 -> tmp/apk_dex_str.txt')


if __name__ == '__main__':
    main()
