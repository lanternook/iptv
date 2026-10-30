#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""push_file.py —— 用 Contents API 推送单个本地文件到仓库（免 clone，适合改配置/更新精选文件）。

用法:
    python tools/push_file.py config/blacklist.txt
    python tools/push_file.py output/curated.txt --message "curated: 移动网络实测精选"
    python tools/push_file.py config/user_demo.txt --repo lanternook/iptv --branch main
"""
import argparse
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gh_api import call  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="相对项目根目录的文件路径，如 config/blacklist.txt")
    ap.add_argument("--repo", default="lanternook/iptv")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--message", default=None)
    a = ap.parse_args()

    local = a.path if os.path.isabs(a.path) else os.path.join(ROOT, a.path)
    if not os.path.exists(local):
        sys.exit("本地文件不存在: %s" % local)
    repo_path = a.path.replace("\\", "/").lstrip("./")
    content = base64.b64encode(open(local, "rb").read()).decode()

    code, raw = call("GET", "/repos/%s/contents/%s?ref=%s" % (a.repo, repo_path, a.branch))
    sha = None
    if code == 200:
        sha = json.loads(raw).get("sha")
    elif code != 404:
        sys.exit("查询远端失败 HTTP %s: %s" % (code, raw[:200]))

    body = {
        "message": a.message or ("update %s" % repo_path),
        "content": content,
        "branch": a.branch,
    }
    if sha:
        body["sha"] = sha

    code, raw = call("PUT", "/repos/%s/contents/%s" % (a.repo, repo_path), body)
    if code in (200, 201):
        print("已推送 %s（%s）" % (repo_path, "更新" if sha else "新增"))
    else:
        print("推送失败 HTTP %s: %s" % (code, raw[:300]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
