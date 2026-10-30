#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""speedtest.py —— 直播源测速与精选（自包含，仅用 Python 标准库）

在本机网络（与电视盒同宽带）实测每条线路的真实下载速率，按 Mbps 降序重排，
输出可直接给 FongMi/TV 订阅的 txt。

为什么需要本机测速：云端 GitHub Actions 在海外，它测出的"最快"对国内移动/电信无意义
（会把跨省 OTT 源、海外中转源排到最前）。本脚本在同网环境实测，结果才反映真实体验。

测速原理：HLS 的 .m3u8 是文本播放列表，下载它测不出速率；必须解析出 .ts 分片再计时下载。

用法:
    python speedtest.py                          # 用 pool.txt 里的源池（最快，不联网）
    python speedtest.py --subscribe              # 从 subscribe.txt 现场抓源建池
    python speedtest.py --src samples/user_result.txt
    python speedtest.py --only CCTV --min-mbps 2.0
    python speedtest.py --limit 40               # 只测前 40 条，快速验证环境

环境要求: Python 3.8+，无第三方依赖。测速强制直连，不走系统代理。
"""
import argparse
import concurrent.futures as cf
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "output")
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"
SAMPLE_SECONDS = 3.0
SAMPLE_BYTES = 2 * 1024 * 1024
CONNECT_TIMEOUT = 5
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 测速：直连
_lock = threading.Lock()


def log(msg):
    with _lock:
        print(msg, flush=True)


def mirrors(url):
    """给出 GitHub raw 的多个镜像，供无代理环境依次尝试。"""
    out = [url]
    if "raw.githubusercontent.com/" in url:
        path = url.split("raw.githubusercontent.com/", 1)[1]
        out.append("https://gh-proxy.com/https://raw.githubusercontent.com/" + path)
        out.append("https://ghfast.top/https://raw.githubusercontent.com/" + path)
        parts = path.split("/")
        if len(parts) >= 4:
            out.append("https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (
                parts[0], parts[1], parts[2], "/".join(parts[3:])))
    return out


def fetch(url, timeout=20, max_bytes=None, deadline=None, use_mirror=False):
    """返回 (bytes, elapsed)。use_mirror=True 时依次尝试镜像。"""
    last = None
    for u in (mirrors(url) if use_mirror else [url]):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            t0 = time.time()
            buf = bytearray()
            with DIRECT.open(req, timeout=timeout) as r:
                while True:
                    chunk = r.read(16384)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if max_bytes is not None and len(buf) >= max_bytes:
                        break
                    if max_bytes is None and len(buf) >= 65536:
                        break
                    if deadline and time.time() >= deadline:
                        break
            return bytes(buf), max(time.time() - t0, 0.001)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("fetch failed")


def resolve_playlist(url, depth=0):
    """m3u8 → 第一个可下载的媒体分片 URL；非 m3u8 原样返回。"""
    if depth > 2:
        return None
    if ".m3u8" not in url.lower() and "m3u8" not in url.lower():
        return url
    try:
        body, _ = fetch(url, CONNECT_TIMEOUT, max_bytes=65536)
    except Exception:  # noqa: BLE001
        return None
    lines = [l.strip() for l in body.decode("utf-8", "replace").splitlines() if l.strip()]
    variants = []
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    variants.append(urllib.parse.urljoin(url, nxt))
                    break
    if variants:
        return resolve_playlist(variants[0], depth + 1)
    for line in lines:
        if not line.startswith("#"):
            return urllib.parse.urljoin(url, line)
    return None


def measure(name, url, seconds, max_bytes):
    seg = resolve_playlist(url)
    if not seg:
        return name, url, 0.0, "解析播放列表失败"
    try:
        data, el = fetch(seg, CONNECT_TIMEOUT, max_bytes=max_bytes, deadline=time.time() + seconds)
    except Exception as e:  # noqa: BLE001
        return name, url, 0.0, "分片请求失败: %s" % type(e).__name__
    if not data:
        return name, url, 0.0, "分片为空"
    return name, url, round(len(data) * 8 / el / 1_000_000, 2), "%dKB/%.1fs" % (len(data) // 1024, el)


def parse_playlist(text):
    """兼容 m3u 与 txt，返回 [(name, url)]。"""
    items, pending = [], None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#EXTINF"):
            m = re.search(r'tvg-name="([^"]+)"', s)
            pending = m.group(1) if m else s.rsplit(",", 1)[-1].strip()
            continue
        if s.startswith("#"):
            continue
        if pending:
            if s.lower().startswith(("http", "rtmp", "rtsp")):
                items.append((pending.strip(), s))
            pending = None
            continue
        if "," in s and "#genre#" not in s:
            n, u = s.split(",", 1)
            u = u.strip()
            if u.lower().startswith(("http", "rtmp", "rtsp")):
                items.append((n.strip(), u))
    return items


CCTV_RE = re.compile(r"^cctv[\s\-_]?(\d{1,2})(\s*\+)?", re.I)
DROP_WORDS = ("高清", "超清", "标清", "蓝光", "hd", "sd", "fhd", "uhd", "频道", "直播", "备用")


def norm_channel(name):
    s = name.strip().replace("（", "(").replace("）", ")")
    m = CCTV_RE.match(s)
    if m:
        return "CCTV-%d%s" % (int(m.group(1)), "+" if m.group(2) else "")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[·\s\-_]", "", s)
    low = s.lower()
    for w in DROP_WORDS:
        low = low.replace(w, "")
    return low


def load_template(path):
    """读频道模板，返回 [(组名, [频道名...])]。"""
    out, cur = [], None
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        if "#genre#" in s:
            cur = s.split(",")[0]
            out.append((cur, []))
            continue
        if cur and "," not in s:
            out[-1][1].append(s)
    return out


def build_from_subscribe(path):
    urls = [l.strip().split()[0] for l in open(path, encoding="utf-8")
            if l.strip() and not l.strip().startswith(("#", "["))]
    allitems = []
    for u in urls:
        try:
            body, _ = fetch(u, 25, use_mirror=True)
            got = parse_playlist(body.decode("utf-8", "replace"))
            allitems.extend(got)
            log("  %-4d 条  %s" % (len(got), u.rsplit("/", 1)[-1]))
        except Exception as e:  # noqa: BLE001
            log("  ERR      %s (%s)" % (u.rsplit("/", 1)[-1], type(e).__name__))
    seen, uniq = set(), []
    for n, u in allitems:
        if (n, u) not in seen:
            seen.add((n, u))
            uniq.append((n, u))
    log("源池合计 %d 条，去重 %d 条" % (len(allitems), len(uniq)))
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.path.join(HERE, "pool.txt"), help="源池快照（默认同目录 pool.txt）")
    ap.add_argument("--subscribe", action="store_true", help="从 subscribe.txt 现场抓源建池")
    ap.add_argument("--src", default=None, help="直接测一个 txt/m3u 文件")
    ap.add_argument("--tpl", default=os.path.join(HERE, "channels.txt"), help="频道模板")
    ap.add_argument("--only", default=None, help="只测规范化后以此开头的频道，如 CCTV")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-mbps", type=float, default=1.5, help="及格线（每台至少保留最快 1 条）")
    ap.add_argument("--per-channel", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=SAMPLE_SECONDS)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    out_path = a.out or os.path.join(OUTDIR, "result_%s.txt" % time.strftime("%Y%m%d_%H%M"))

    # 1) 取数据
    if a.src:
        text = open(a.src, encoding="utf-8", errors="replace").read()
        log("输入文件: %s" % a.src)
        groups, cur, meta = [], None, []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if "#genre#" in s:
                name = s.split(",")[0]
                if "更新时间" in name:
                    meta.append(s)
                    cur = "__META__"
                    continue
                cur = name
                groups.append([name, []])
                continue
            if "," in s:
                if cur == "__META__":
                    meta.append(s)
                    continue
                if cur:
                    n, u = s.split(",", 1)
                    u = u.strip()
                    if u.lower().startswith(("http", "rtmp", "rtsp")):
                        groups[-1][1].append((n.strip(), u))
    else:
        if a.subscribe:
            log("从 subscribe.txt 现场抓源:")
            pool = build_from_subscribe(os.path.join(HERE, "subscribe.txt"))
        else:
            if not os.path.exists(a.pool):
                sys.exit("找不到源池 %s，改用 --subscribe 现场抓源" % a.pool)
            log("读取源池: %s" % a.pool)
            pool = parse_playlist(open(a.pool, encoding="utf-8", errors="replace").read())
        tpl = load_template(a.tpl)
        index = {}
        for gname, names in tpl:
            for n in names:
                index.setdefault(norm_channel(n), (gname, n))
        pos = {g: i for i, (g, _) in enumerate(tpl)}
        groups, meta = [[g, []] for g, _ in tpl], []
        hit = miss = 0
        for n, u in pool:
            tgt = index.get(norm_channel(n))
            if not tgt:
                miss += 1
                continue
            groups[pos[tgt[0]]][1].append((tgt[1], u))
            hit += 1
        log("按模板归类：命中 %d 条，丢弃 %d 条（模板外频道）" % (hit, miss))

    if a.only:
        want = a.only.upper()
        for g in groups:
            g[1] = [(n, u) for n, u in g[1] if norm_channel(n).upper().startswith(want)]
        log("--only %s 过滤后剩余 %d 条" % (a.only, sum(len(g[1]) for g in groups)))

    flat = [(n, u, gi) for gi, g in enumerate(groups) for (n, u) in g[1]]
    if a.limit:
        flat = flat[:a.limit]
    if not flat:
        sys.exit("没有可测线路，检查模板/源池/--only")

    log("待测 %d 条，并发 %d，单条采样 %.0f 秒，预计 %.0f 分钟" % (
        len(flat), a.workers, a.seconds, len(flat) * (a.seconds + 0.6) / a.workers / 60))

    # 2) 并发测速
    results, done, t_all = [], 0, time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(measure, n, u, a.seconds, SAMPLE_BYTES): (n, u, gi) for n, u, gi in flat}
        for fut in cf.as_completed(futs):
            n, u, gi = futs[fut]
            try:
                _, _, mbps, note = fut.result()
            except Exception as e:  # noqa: BLE001
                mbps, note = 0.0, type(e).__name__
            results.append((gi, n, u, mbps))
            done += 1
            if done % 20 == 0 or done == len(flat):
                ok = sum(1 for r in results if r[3] >= a.min_mbps)
                log("  进度 %d/%d  达标 %d  已用 %.0fs" % (done, len(flat), ok, time.time() - t_all))

    # 3) 每台取前 N 条
    by_group = {}
    for gi, n, u, mbps in results:
        by_group.setdefault(gi, {}).setdefault(n, []).append((mbps, u))

    # 频道顺序按模板（channels.txt）排，避免并发完成顺序导致的随机次序
    tmpl_rank = {}
    for gi, g in enumerate(groups):
        for i, (n, _u) in enumerate(g[1]):
            tmpl_rank.setdefault(gi, {}).setdefault(n, i)

    lines = meta[:] if meta else ["🕘️更新时间,#genre#",
                                  "%s,https://example.com/ping" % time.strftime("%Y-%m-%d %H:%M:%S")]
    kept = 0
    for gi, g in enumerate(groups):
        chans = by_group.get(gi, {})
        rank = tmpl_rank.get(gi, {})
        out_lines = []
        for n in sorted(chans.keys(), key=lambda x: rank.get(x, 1 << 30)):
            items = chans[n]
            items.sort(key=lambda x: -x[0])
            good = [x for x in items if x[0] >= a.min_mbps][: a.per_channel]
            if not good and items:
                good = items[:1]
            for mbps, u in good:
                out_lines.append("%s,%s" % (n, u))
                kept += 1
        if out_lines:
            lines.append("%s,#genre#" % g[0])
            lines.extend(out_lines)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    log("-" * 56)
    log("保留 %d 条（原始 %d 条），耗时 %.0f 秒" % (kept, len(flat), time.time() - t_all))
    log("已写入 %s" % out_path)
    log("各台首选速率（Mbps）：")
    for gi, g in enumerate(groups):
        for n, items in by_group.get(gi, {}).items():
            items.sort(key=lambda x: -x[0])
            log("  %-10s %6.2f  %s" % (n, items[0][0], items[0][1][:60]))
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
