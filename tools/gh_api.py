#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 GitHub API 客户端（走 Clash 代理）。

用法:
    python tools/gh_api.py GET  /user
    python tools/gh_api.py POST /repos/Guovin/iptv-api/forks
    python tools/gh_api.py PUT  /repos/u/r/actions/permissions --body '{"enabled":true}'

Token 读取顺序: 环境变量 GITHUB_TOKEN -> 同目录 token.txt。
"""
import json
import os
import sys
import urllib.error
import urllib.request

PROXY = os.environ.get("GITHUB_PROXY", "http://127.0.0.1:7897")
API = "https://api.github.com"


def token():
    t = os.environ.get("GITHUB_TOKEN")
    if t:
        return t.strip()
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    sys.exit("缺少 token: 设置 GITHUB_TOKEN 或写入 tools/token.txt")


def opener():
    h = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
    return urllib.request.build_opener(h)


def call(method, path, body=None, timeout=30):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "iptv-url-gen")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with opener().open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--scopes":
        req = urllib.request.Request(API + "/user")
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("User-Agent", "iptv-url-gen")
        with opener().open(req, timeout=20) as r:
            print("login:", json.loads(r.read().decode()).get("login"))
            print("x-oauth-scopes:", r.headers.get("x-oauth-scopes") or "(fine-grained token，无 scopes 头)")
            print("x-accepted-oauth-scopes:", r.headers.get("x-accepted-oauth-scopes"))
        return
    method, path = sys.argv[1].upper(), sys.argv[2]
    body = None
    if "--body" in sys.argv:
        body = json.loads(sys.argv[sys.argv.index("--body") + 1])
    code, raw = call(method, path, body)
    print("HTTP", code)
    try:
        print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2)[:3000])
    except Exception:
        print(raw[:3000])


if __name__ == "__main__":
    main()
