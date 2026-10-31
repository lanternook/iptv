#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""local_speedtest.py —— 在「本机网络」（与电视盒同宽带）实测每条线路的真实下载速率，
按 Mbps 降序重排，生成 output/curated.txt 作为主订阅。

为什么需要它：云端 Actions 在海外测速，选出的"最快"对国内移动/电信网络无意义
（会把跨省 OTT 源、海外中转源排到最前）。只有在本机实测，排序才反映真实体验。

测速原理：HLS 的 .m3u8 是文本播放列表，下载它测不出速率，必须解析出 .ts 分片再计时下载。
  1. 取 m3u8 → 若是 master playlist（含 #EXT-X-STREAM-INF）取第一个变体
  2. 取子 playlist 中第一个分片 URL
  3. 下载该分片，最多 3 秒 / 2MB，按 字节数÷耗时 折算 Mbps

用法:
    python tools/local_speedtest.py                     # 拉云端候选池 → 实测 → 生成 curated.txt
    python tools/local_speedtest.py --src output/user_result.txt
    python tools/local_speedtest.py --min-mbps 2.0 --per-channel 5 --workers 6
    python tools/local_speedtest.py --limit 40          # 只测前 40 条，快速试跑

注意:
    - 强制直连，不走 Clash 代理（否则测的是代理速度，结果无意义）
    - 测速期间别同时看视频/下载，否则带宽被抢，结果偏低
    - 并发默认 6，太高会互相抢带宽导致全部测不准
"""
import argparse
import concurrent.futures as cf
import json
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
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "output", "curated.txt")
UA = "Mozilla/5.0 (Linux; Android 7.0) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"
SAMPLE_SECONDS = 3.0
SAMPLE_BYTES = 2 * 1024 * 1024
CONNECT_TIMEOUT = 5
_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def opener(use_proxy=False):
    """测速必须直连（否则测的是代理速度）；只有拉云端 txt 时才走本机代理。"""
    if use_proxy:
        p = os.environ.get("IPTV_PROXY", "http://127.0.0.1:7897")
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": p, "https": p}))
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


OP = opener(False)
OP_PROXY = opener(True)


def http_get(url, timeout, max_bytes=None, deadline=None, use_proxy=False):
    """返回 (bytes, elapsed)。deadline 为绝对时间戳，到点即停。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    op = OP_PROXY if use_proxy else OP
    t0 = time.time()
    total = 0
    buf = bytearray()
    with op.open(req, timeout=timeout) as r:
        while True:
            chunk = r.read(16384)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is None:
                buf.extend(chunk)
                if total >= 65536:
                    break
            else:
                buf.extend(chunk)
                if total >= max_bytes:
                    break
                if deadline and time.time() >= deadline:
                    break
    return bytes(buf), max(time.time() - t0, 0.001)


def resolve_playlist(url, depth=0):
    """把 m3u8 解析成第一个可下载的媒体分片 URL；非 m3u8 原样返回。"""
    if depth > 2:
        return None
    low = url.lower()
    if ".m3u8" not in low and "m3u8" not in low:
        return url  # ts / flv / mp4 直接测
    try:
        body, _ = http_get(url, CONNECT_TIMEOUT)
        text = body.decode("utf-8", "replace")
    except Exception:
        return None

    base = url
    variants = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    variants.append(urllib.parse.urljoin(base, nxt))
                    break
    if variants:
        return resolve_playlist(variants[0], depth + 1)

    # 媒体播放列表：取第一个非注释行（即分片 URI）
    for line in lines:
        if line.startswith("#"):
            continue
        return urllib.parse.urljoin(base, line)
    return None


def measure(item, sample_seconds, sample_bytes):
    """返回 (name, url, mbps, note)。"""
    name, url = item
    t0 = time.time()
    seg = resolve_playlist(url)
    if not seg:
        return name, url, 0.0, "解析播放列表失败"
    deadline = time.time() + sample_seconds
    try:
        data, elapsed = http_get(seg, CONNECT_TIMEOUT, max_bytes=sample_bytes, deadline=deadline)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, OSError) as e:
        return name, url, 0.0, "分片请求失败: %s" % type(e).__name__
    if not data:
        return name, url, 0.0, "分片为空"
    mbps = len(data) * 8 / elapsed / 1_000_000
    return name, url, round(mbps, 2), "%dKB/%.1fs" % (len(data) // 1024, elapsed)


def cloud_url():
    p = os.path.join(HERE, "site.json")
    cfg = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        cfg.get("user", "lanternook"), cfg.get("repo", "iptv"),
        cfg.get("branch", "main"), cfg.get("file", "output/user_result.txt"))


def parse_playlist(text):
    """同时兼容 m3u 与 txt，返回 [(name, url)]。"""
    items = []
    pending = None
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


def fetch_source(u, timeout=25):
    """抓订阅源，直连失败自动走镜像。返回 (text, 镜像名)。"""
    cands = [("直连", u)]
    if "raw.githubusercontent.com/" in u:
        rest = u.split("raw.githubusercontent.com/", 1)[1]
        cands.append(("ghfast", "https://ghfast.top/https://raw.githubusercontent.com/" + rest))
        cands.append(("gh-proxy", "https://gh-proxy.com/https://raw.githubusercontent.com/" + rest))
    last = None
    for tag, url in cands:
        try:
            body, _ = http_get(url, timeout, max_bytes=None, use_proxy=True)
            if body and len(body) > 200:
                return body.decode("utf-8", "replace"), tag
        except Exception as e:  # noqa: BLE001
            last = e
    raise last or RuntimeError("空响应")


def build_from_subscribe(template_names=None):
    """从 config/subscribe.txt + subscribe_pool.txt 现场建池。

    订阅源每日更新，每次跑都重新抓，源池才是最新的（不是读静态快照）。
    聚合池（subscribe_pool.txt）条目量大，只保留模板里有的频道名，避免测速爆炸。
    """
    files = ["subscribe.txt", "subscribe_pool.txt"]
    urls = []
    for fn in files:
        p = os.path.join(ROOT, "config", fn)
        if not os.path.exists(p):
            continue
        for l in open(p, encoding="utf-8"):
            s = l.strip()
            if s and not s.startswith(("#", "[")):
                urls.append((fn, s.split()[0]))

    allitems = []
    for fn, u in urls:
        try:
            text, mirror = fetch_source(u)
            got = parse_playlist(text)
            raw_n = len(got)
            if fn == "subscribe_pool.txt" and template_names:
                got = [(n, x) for n, x in got if norm_channel(n) in template_names]
            allitems.extend(got)
            log("  %-5d 条(模板命中 %d)  %-6s %s" % (raw_n, len(got), mirror, u.rsplit("/", 1)[-1][:40]))
        except Exception as e:  # noqa: BLE001
            log("  ERR        %-6s %s (%s)" % ("-", u.rsplit("/", 1)[-1][:40], type(e).__name__))

    seen, uniq = set(), []
    for n, u in allitems:
        k = (n, u)
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    log("源池合计 %d 条，去重 %d 条" % (len(allitems), len(uniq)))
    return uniq


CCTV_RE = re.compile(r"^cctv[\s\-_]?(\d{1,2})(\s*\+)?", re.I)
DROP_WORDS = ("高清", "超清", "标清", "蓝光", "hd", "sd", "fhd", "uhd", "频道", "直播", "备用")


def norm_channel(name):
    """把候选频道名规范化：CCTV1综合/CCTV-1 (720p)/CCTV1 → CCTV-1；其余去后缀词与标点。"""
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


def load_template_groups():
    """读 config/user_demo.txt，返回 [(组名, [频道名...])]。"""
    out, cur = [], None
    p = os.path.join(ROOT, "config", "user_demo.txt")
    for line in open(p, encoding="utf-8"):
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


def group_by_template(items):
    """把扁平候选池按模板分组归类，返回 groups / meta。"""
    tpl = load_template_groups()
    index = {}
    for gname, names in tpl:
        for n in names:
            index.setdefault(norm_channel(n), (gname, n))
    groups = [[g, []] for g, _ in tpl]
    pos = {g: i for i, (g, _) in enumerate(tpl)}
    hit = miss = 0
    for n, u in items:
        key = norm_channel(n)
        tgt = index.get(key)
        if not tgt:
            miss += 1
            continue
        gname, canon = tgt
        groups[pos[gname]][1].append((canon, u))
        hit += 1
    log("按模板归类：命中 %d 条，丢弃 %d 条（模板外频道）" % (hit, miss))
    return groups, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--from-subscribe", action="store_true",
                    help="直接从 config/subscribe.txt 的源建池（不经过云端测速淘汰，能捞回被误杀的国内好源）")
    ap.add_argument("--only", default=None, help="只测频道名规范化后以此开头的（如 CCTV）")
    ap.add_argument("--extra", default=None, help="额外源文件（name,url 每行一条），并入候选池")
    ap.add_argument("--tpl", default=os.path.join(ROOT, "config", "user_demo.txt"), help="频道模板")
    ap.add_argument("--out", default=None, help="输出路径，默认 output/curated.txt")
    ap.add_argument("--min-mbps", type=float, default=1.5, help="及格线，低于此值不入选（每台至少保留最快 1 条）")
    ap.add_argument("--per-channel", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=SAMPLE_SECONDS)
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 条，用于快速试跑")
    ap.add_argument("--strict-group", action="append", default=["卫视"],
                    help="该组不保底：全台低于门槛就整台丢弃，可多次；默认 卫视")
    ap.add_argument("--rates", default=os.path.join(ROOT, "output", "rates.tsv"),
                    help="速率索引输出路径，供 merge_tv.py 过滤用")
    a = ap.parse_args()

    global OUT
    if a.out:
        OUT = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)

    if a.from_subscribe:
        log("从订阅源现场建池（每次重新抓，源池即最新）:")
        tpl_groups = load_template_groups()
        tpl_names = {norm_channel(n) for _g, items in tpl_groups for n in items}
        groups, meta = group_by_template(build_from_subscribe(tpl_names))
    else:
        if a.src:
            txt = open(a.src, encoding="utf-8", errors="replace").read()
            log("输入: %s" % a.src)
        else:
            u = cloud_url()
            log("拉取云端候选池: %s" % u)
            body, _ = http_get(u, 20, max_bytes=None, use_proxy=True)
            txt = body.decode("utf-8", "replace")

        groups, cur, meta = [], None, []
        for line in txt.splitlines():
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

    if a.extra:
        extra_items = parse_playlist(open(a.extra, encoding="utf-8").read())
        tpl = load_template_groups()
        index = {}
        for gname, names in tpl:
            for n in names:
                index.setdefault(norm_channel(n), (gname, n))
        gmap = {g[0]: g for g in groups}
        for gname, _ in tpl:
            if gname not in gmap:
                groups.append([gname, []])
                gmap[gname] = groups[-1]
        added = 0
        for n, u in extra_items:
            tgt = index.get(norm_channel(n))
            if not tgt:
                continue
            bucket = gmap[tgt[0]][1]
            if (tgt[1], u) in bucket:  # 池里已有同一条，不重复加
                continue
            bucket.append((tgt[1], u))
            added += 1
        log("追加外部源 %d 条，按模板命中 %d 条" % (len(extra_items), added))

    if a.only:
        want = a.only.upper()
        for g in groups:
            g[1] = [(n, u) for n, u in g[1] if norm_channel(n).upper().startswith(want)]
        log("--only %s 过滤后剩余 %d 条" % (a.only, sum(len(g[1]) for g in groups)))

    flat = [(n, u, gi) for gi, g in enumerate(groups) for (n, u) in g[1]]
    if a.limit:
        flat = flat[:a.limit]
    log("待测线路 %d 条（分组 %d 个），并发 %d，单条采样 %.0f 秒，预计 %.0f 分钟" % (
        len(flat), len(groups), a.workers, a.seconds,
        len(flat) * (a.seconds + 0.6) / a.workers / 60))

    results = []
    done = 0
    t_all = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(measure, (n, u), a.seconds, SAMPLE_BYTES): (n, u, gi) for n, u, gi in flat}
        for fut in cf.as_completed(futs):
            n, u, gi = futs[fut]
            try:
                _, _, mbps, note = fut.result()
            except Exception as e:  # noqa: BLE001
                mbps, note = 0.0, type(e).__name__
            results.append((gi, n, u, mbps, note))
            done += 1
            if done % 20 == 0 or done == len(flat):
                ok = sum(1 for r in results if r[3] >= a.min_mbps)
                log("  进度 %d/%d  达标 %d  已用 %.0fs" % (done, len(flat), ok, time.time() - t_all))

    # 每台按速率降序取前 N 条，低于及格线的只保留最快 1 条
    by_group = {}
    tmpl_rank = {}
    for gi, n, u, mbps, note in results:
        by_group.setdefault(gi, {}).setdefault(n, []).append((mbps, u, note))
    # 频道顺序按模板排，避免并发完成顺序导致的随机次序
    for gi, g in enumerate(groups):
        for i, (n, _u) in enumerate(g[1]):
            tmpl_rank.setdefault(gi, {}).setdefault(n, i)

    lines = meta[:] if meta else ["🕘️更新时间,#genre#"]
    if not meta:
        lines.append("%s,https://cdn.jsdelivr.net/gh/lanternook/iptv@main/output/curated.txt"
                     % time.strftime("%Y-%m-%d %H:%M:%S"))
    kept = total = 0
    summary = []
    dropped_low = []
    for gi, g in enumerate(groups):
        chans = by_group.get(gi, {})
        rank = tmpl_rank.get(gi, {})
        strict = any(k in g[0] for k in a.strict_group)
        out_lines = []
        for n in sorted(chans.keys(), key=lambda x: rank.get(x, 1 << 30)):
            items = chans[n]
            items.sort(key=lambda x: -x[0])
            good = [x for x in items if x[0] >= a.min_mbps][: a.per_channel]
            if not good and items and not strict:
                good = items[:1]  # 非严格组全不达标也留最快一条，避免整台消失
            if not good:
                if items:
                    dropped_low.append("%s(%.2f)" % (n, items[0][0]))
                continue
            for mbps, u, _ in good:
                out_lines.append("%s,%s" % (n, u))
                kept += 1
            total += 1
        if out_lines:
            lines.append("%s,#genre#" % g[0])
            lines.extend(out_lines)
        summary.append((g[0], len(chans), len(out_lines)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # 速率索引：merge_tv.py 据此过滤低速率线路
    try:
        os.makedirs(os.path.dirname(a.rates), exist_ok=True)
        with open(a.rates, "w", encoding="utf-8") as f:
            f.write("# name\tmbps\turl\n")
            for _gi, n, u, mbps, _note in results:
                f.write("%s\t%.3f\t%s\n" % (n, mbps, u))
    except Exception as e:  # noqa: BLE001
        log("速率表写入失败: %s" % e)

    log("-" * 56)
    for gname, ch, ln in summary:
        log("  %-10s %2d 台  %3d 条" % (gname, ch, ln))
    if dropped_low:
        log("  严格组丢弃 %d 台（<%.1f Mbps）: %s"
            % (len(dropped_low), a.min_mbps, ",".join(dropped_low)))
    log("保留 %d 条（原始 %d 条），耗时 %.0f 秒" % (kept, len(flat), time.time() - t_all))
    log("已写入 %s" % OUT)

    # 打印各台第一条（即播放器默认播的那条）的速率，便于肉眼判断
    log("-" * 56)
    log("各台首选线路速率（Mbps）：")
    for gi, g in enumerate(groups):
        chans = by_group.get(gi, {})
        for n, items in list(chans.items())[:40]:
            items.sort(key=lambda x: -x[0])
            log("  %-10s %5.2f  %s" % (n, items[0][0], items[0][1][:58]))
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
