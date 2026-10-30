#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮询 GitHub Actions 运行状态，结束后打印各步骤结论与失败日志尾部。

用法: python tools/watch_run.py [--repo lanternook/iptv] [--run-id N] [--timeout 3600]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7897"
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))


def token():
    import os
    return open(os.path.join(HERE, "token.txt"), encoding="utf-8").read().strip()


def get(path):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
    req = urllib.request.Request("https://api.github.com" + path)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "iptv-watch")
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 不自动跟随，交由调用方处理（跨域时 Authorization 会被丢弃导致 401）


def raw_logs(repo, job_id):
    url = "https://api.github.com/repos/%s/actions/jobs/%s/logs" % (repo, job_id)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}), _NoRedirect())
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("User-Agent", "iptv-watch")
    try:
        with op.open(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if e.code in (301, 302, 303, 307) and loc:
            try:
                req2 = urllib.request.Request(loc)
                req2.add_header("User-Agent", "iptv-watch")
                with urllib.request.build_opener(
                    urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
                ).open(req2, timeout=90) as r2:
                    return r2.read().decode("utf-8", "replace")
            except Exception as e2:  # noqa: BLE001
                return "(日志下载失败: %s)" % e2
        return "(取日志失败 HTTP %s)" % e.code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="lanternook/iptv")
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()

    rid = a.run_id
    t0 = time.time()
    while True:
        if not rid:
            _, d = get("/repos/%s/actions/runs?per_page=1" % a.repo)
            runs = d.get("workflow_runs") or []
            if not runs:
                print("暂无运行记录")
                return 1
            rid = runs[0]["id"]
        _, d = get("/repos/%s/actions/runs/%s" % (a.repo, rid))
        st, cc = d.get("status"), d.get("conclusion")
        el = int(time.time() - t0)
        print("[%4ds] run %s status=%s conclusion=%s" % (el, rid, st, cc))
        if st == "completed":
            break
        if el > a.timeout:
            print("超时退出，运行仍在进行")
            return 2
        time.sleep(60)

    _, jobs = get("/repos/%s/actions/runs/%s/jobs" % (a.repo, rid))
    fail_job = None
    for j in jobs.get("jobs", []):
        print("\nJOB %s -> %s" % (j["name"], j.get("conclusion")))
        for s in j.get("steps", []):
            print("  %-8s %s" % (s.get("conclusion"), s["name"]))
            if s.get("conclusion") == "failure" and not fail_job:
                fail_job = j["id"]
    if fail_job:
        print("\n===== 失败步骤日志尾部 =====")
        log = raw_logs(a.repo, fail_job)
        print("\n".join(log.splitlines()[-40:]))
    return 0 if cc == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
