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

PROXY = os.environ.get("GITHUB_PROXY", "")   # 空=自动；填 none=强制直连
LOCAL_PROXY = "http://127.0.0.1:7897"
API = "https://api.github.com"


def _opener(proxy):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _port_open(host, port, timeout=0.4):
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        s.close()


def _candidates():
    """返回按优先级尝试的通道。

    本机装了 Clash（7897 可连）就优先走代理；新机器没代理则直连。
    GITHUB_PROXY=none 强制直连，GITHUB_PROXY=<url> 强制指定。
    """
    if PROXY.lower() in ("none", "direct", "0"):
        return [None]
    if PROXY:
        return [PROXY]
    if _port_open("127.0.0.1", 7897):
        return [LOCAL_PROXY, None]
    return [None]


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
    return _opener(_candidates()[0])


def call(method, path, body=None, timeout=30):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for proxy in _candidates():
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "iptv-url-gen")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with _opener(proxy).open(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                if url.startswith(API):
                    try:
                        json.loads(body)
                    except Exception:  # noqa: BLE001
                        # 被劫持/重定向后的 HTML，换个通道再来
                        last = RuntimeError("非 JSON 响应（疑似被劫持）")
                        continue
                return r.status, body
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                # 直连被劫持/重定向（PUT 不会自动跟随），换下一个通道
                last = e
                continue
            # 服务端已正常应答（401/403/404 等），换代理无意义
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001  连接层失败才换下一个
            last = e
    return 0, "连接失败（直连与本地代理都不通）: %s" % last


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
