#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""push_file.py —— 用 Contents API 推送文件到仓库（免 clone）。

推送配置集中在 config/publish.json（user/repo/branch/token/message/files）。

用法:
    python tools/push_file.py                      # 按 publish.json 的 files 全部推送
    python tools/push_file.py config/blacklist.txt # 推单个文件
    python tools/push_file.py output/curated.txt --message "curated: 刷新"
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gh_api import call  # noqa: E402

CFG = os.path.join(ROOT, "config", "publish.json")


def load_cfg():
    if not os.path.exists(CFG):
        return {}
    try:
        return json.load(open(CFG, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def push_one(path, repo, branch, message):
    local = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(local):
        print("跳过（本地不存在）: %s" % path)
        return 0
    repo_path = path.replace("\\", "/").lstrip("./")
    # 中文/空格路径需 percent-encode，否则 urllib 在拼 URL 时按 ascii 编码报错
    repo_url_path = urllib.parse.quote(repo_path)
    content = base64.b64encode(open(local, "rb").read()).decode()

    code, raw = call("GET", "/repos/%s/contents/%s?ref=%s" % (repo, repo_url_path, branch))
    sha = None
    if code == 200:
        sha = json.loads(raw).get("sha")
    elif code != 404:
        print("查询远端失败 HTTP %s: %s" % (code, raw[:200]))
        return 1

    body = {
        "message": message or ("update %s" % repo_path),
        "content": content,
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    code, raw = call("PUT", "/repos/%s/contents/%s" % (repo, repo_url_path), body)
    if code in (200, 201):
        print("已推送 %s（%s）" % (repo_path, "更新" if sha else "新增"))
        return 0
    print("推送失败 %s HTTP %s: %s" % (repo_path, code, raw[:300]))
    return 1


def main():
    cfg = load_cfg()
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="单个文件路径；省略则推 publish.json 里的 files")
    ap.add_argument("--repo", default="%s/%s" % (cfg.get("user", "lanternook"), cfg.get("repo", "iptv")))
    ap.add_argument("--branch", default=cfg.get("branch", "main"))
    ap.add_argument("--message", default=cfg.get("message"))
    a = ap.parse_args()

    targets = [a.path] if a.path else (cfg.get("files") or ["output/curated.txt"])
    rc = 0
    for p in targets:
        rc |= push_one(p, a.repo, a.branch, a.message)
    return rc


if __name__ == "__main__":
    sys.exit(main())
