#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bootstrap_repo.py —— 把 iptv-api 上游源码 + 本项目配置推送到你的 GitHub 仓库。

前置（必须先在浏览器完成，见 README）：
  1. 新建空仓库（建议名 iptv，public，不要勾 README/.gitignore）
  2. 在网页新建 .github/workflows/update-cron.yml 并粘贴本项目同名文件内容
     （本机 PAT 若没有 Workflows 写权限，git 无法推送 workflow 文件）

用法:
    python tools/bootstrap_repo.py --user lanternook --repo iptv
    python tools/bootstrap_repo.py --user lanternook --repo iptv --ref 1.7.2   # 回退旧版（自带 cron 工作流）
    python tools/bootstrap_repo.py --user lanternook --repo iptv --dry-run     # 只准备目录不推送
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "build")
PROXY = os.environ.get("GITHUB_PROXY", "http://127.0.0.1:7897")
UPSTREAM = "Guovin/iptv-api"
SKIP_TOP = {".github", ".git", "output", "release-assets"}


def token():
    p = os.path.join(HERE, "token.txt")
    t = os.environ.get("GITHUB_TOKEN") or (open(p, encoding="utf-8").read().strip() if os.path.exists(p) else "")
    if not t:
        sys.exit("缺少 token：设置 GITHUB_TOKEN 或写入 tools/token.txt")
    return t


def api(path, tok):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
    req = urllib.request.Request("https://api.github.com" + path)
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "iptv-bootstrap")
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def run(cmd, cwd, env=None):
    e = dict(os.environ)
    e.update({"https_proxy": PROXY, "http_proxy": PROXY, "GIT_TERMINAL_PROMPT": "0"})
    if env:
        e.update(env)
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("命令失败: %s\n%s\n%s" % (" ".join(cmd), p.stdout[-1500:], p.stderr[-1500:]))
        sys.exit(1)
    return p.stdout


def fetch_upstream(ref, dest):
    url = "https://codeload.github.com/%s/tar.gz/refs/heads/%s" % (UPSTREAM, ref)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
    print("下载上游源码 %s ..." % url)
    with op.open(url, timeout=120) as r:
        raw = r.read()
    print("  体积 %.1f MB" % (len(raw) / 1048576))
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name.count("/") >= 1 and m.name.split("/", 1)[1].split("/")[0] not in SKIP_TOP]
        tf.extractall(dest, members=members, filter="data")
    roots = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
    return os.path.join(dest, roots[0])


def ensure_workflow(user, repo, branch, tok):
    """通过 API 上传 .github/workflows/update-cron.yml（需 token 具备 workflow 权限）。"""
    import base64
    path = ".github/workflows/update-cron.yml"
    src = os.path.join(ROOT, ".github", "workflows", "update-cron.yml")
    code, info = api("/repos/%s/%s/contents/%s?ref=%s" % (user, repo, path, branch), tok)
    if code == 200:
        print("仓库已有 workflow 文件，跳过上传")
        return True
    if code not in (404,):
        print("查询 workflow 失败 HTTP %s: %s" % (code, info.get("message")))
        return False
    content = base64.b64encode(open(src, "rb").read()).decode()
    code, info = api_put("/repos/%s/%s/contents/%s" % (user, repo, path), tok, {
        "message": "ci: add scheduled playlist update",
        "content": content,
        "branch": branch,
    })
    if code in (200, 201):
        print("已通过 API 创建 %s" % path)
        return True
    print("!! 上传 workflow 失败 HTTP %s: %s（token 需 workflow 权限；可改为网页手工创建）" % (code, info.get("message")))
    return False


def ensure_actions_write(user, repo, tok):
    code, info = api_put("/repos/%s/%s/actions/permissions/workflow" % (user, repo), tok,
                         {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": False})
    print("工作流写权限: %s" % ("已设为 write" if code in (200, 204) else "设置失败 HTTP %s（可在 Settings→Actions 手动改）" % code))


def api_put(path, tok, body):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))
    req = urllib.request.Request("https://api.github.com" + path, data=json.dumps(body).encode(), method="PUT")
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "iptv-bootstrap")
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--repo", default="iptv")
    ap.add_argument("--ref", default="master", help="上游分支或标签，默认 master")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tok = token()
    code, info = api("/repos/%s/%s" % (a.user, a.repo), tok)
    if code == 404:
        sys.exit("仓库 %s/%s 不存在。请先在浏览器新建空仓库（不要勾选 README），再重跑本脚本。" % (a.user, a.repo))
    if code != 200:
        sys.exit("读取仓库信息失败 HTTP %s: %s" % (code, info.get("message")))
    branch = info.get("default_branch") or "master"
    print("目标仓库: %s/%s  默认分支: %s" % (a.user, a.repo, branch))

    work = os.path.join(BUILD, a.repo)
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(BUILD, exist_ok=True)
    print("克隆目标仓库 ...")
    run(["git", "clone", "--depth", "1", "https://x-access-token:%s@github.com/%s/%s.git" % (tok, a.user, a.repo), work], BUILD)

    src = fetch_upstream(a.ref, os.path.join(BUILD, "_upstream"))
    print("覆盖上游文件 ...")
    n = 0
    for name in os.listdir(src):
        if name in SKIP_TOP:
            continue
        s, d = os.path.join(src, name), os.path.join(work, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
        n += 1
    print("  已同步 %d 个顶层条目" % n)

    print("写入本项目配置 ...")
    for f in ("user_demo.txt", "subscribe.txt", "user_config.ini"):
        shutil.copy2(os.path.join(ROOT, "config", f), os.path.join(work, "config", f))
        print("  config/" + f)

    has_wf = os.path.exists(os.path.join(work, ".github", "workflows", "update-cron.yml"))
    if not has_wf:
        print("仓库内暂无 workflow 文件，尝试通过 API 上传 ...")
        has_wf = ensure_workflow(a.user, a.repo, branch, tok)

    if a.dry_run:
        print("dry-run: 内容已准备在 %s，未提交" % work)
        return

    run(["git", "config", "user.name", "lanternook"], work)
    run(["git", "config", "user.email", "lanternook@users.noreply.github.com"], work)
    run(["git", "add", "-A"], work)
    p = subprocess.run(["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True)
    if not p.stdout.strip():
        print("无变更，跳过提交")
    else:
        print("变更文件数: %d" % len(p.stdout.strip().splitlines()))
        run(["git", "commit", "-m", "chore: overlay iptv config (%s)" % a.ref], work)
        run(["git", "push", "origin", "HEAD:%s" % branch], work)
        print("推送完成")

    shutil.rmtree(os.path.join(BUILD, "_upstream"), ignore_errors=True)
    ensure_actions_write(a.user, a.repo, tok)
    print("\n下一步: 打开 https://github.com/%s/%s/actions 手动 Run 一次 `Update playlist`" % (a.user, a.repo))
    print("然后把分支名记进 tools/site.json: python tools/iptv_url_gen.py --save-user %s --save-repo %s (branch=%s)" % (a.user, a.repo, branch))


if __name__ == "__main__":
    main()
