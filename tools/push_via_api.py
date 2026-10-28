"""github.com 的 443 被代理掐断时，用 Git Data API 把本地未推送的提交重放上去。

    python tools/push_via_api.py luck-l6/DeskDock main

为什么需要它：这台机器上 `github.com:443` 经常 `CONNECT tunnel failed, 502`
或 `schannel: server closed abruptly`，`git push` 直接失败；但 `api.github.com`
是通的，`gh` 也已登录（repo scope）。于是改走 REST：blob → tree(base_tree =
远端头) → commit(parents=[远端头]) → PATCH ref，一个提交一个提交地重放。

两点注意：
- 本地提交 sha 和远端不会一致（committer 时间戳不同）。内容是否一致用
  `git rev-parse HEAD^{tree}` 和远端 commit 的 `tree.sha` 比。网络恢复后本地
  要么 `git reset --hard origin/main`（内容相同，安全），要么 force push。
- Release 资产上传走 uploads.github.com，**不受** github.com 被断的影响。

只处理文本文件的新增/修改/删除，二进制会按 utf-8 读坏 —— 需要时先改成
二进制 base64 方案。
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys


def gh(path: str, method: str = "GET", body: dict | None = None) -> dict:
    cmd = ["gh", "api", "-X", method, path,
           "-H", "Accept: application/vnd.github+json"]
    if body is not None:
        cmd += ["--input", "-"]
    out = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else None,
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise RuntimeError(f"{method} {path} 失败: {out.stderr.strip()}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def git_bytes(*args: str) -> bytes:
    """拿原始字节。不能带 text=True：那会把 \\r\\n 归一成 \\n，内容就变了。"""
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def changed(commit: str) -> list[tuple[str, str]]:
    rows = []
    for line in git("diff-tree", "--no-commit-id", "--name-status", "-r",
                    commit).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0][0], parts[-1]))
    return rows


def main() -> int:
    repo, branch = sys.argv[1], sys.argv[2]
    head = gh(f"repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]
    # 远端头常常是上一次**由本脚本创建**的提交，本地压根没这个对象，
    # `git rev-list 远端头..HEAD` 会直接失败。这时要显式给本地起点：
    # 传上次推过的那个本地提交（见脚本末尾打印的本地 sha）。
    try:
        pending = git("rev-list", "--reverse", f"{head}..HEAD").split()
    except subprocess.CalledProcessError:
        if len(sys.argv) < 4:
            raise SystemExit(
                "本地没有远端头这个对象，需要补一个本地起点：\n"
                f"  python tools/push_via_api.py {repo} {branch} <上次推过的本地提交>")
        pending = git("rev-list", "--reverse", f"{sys.argv[3]}..HEAD").split()
    if not pending:
        print("没有待推送的提交")
        return 0
    print("远端头:", head)
    print("待推:", len(pending), "个提交")

    for commit in pending:
        msg = git("log", "-1", "--format=%B", commit).rstrip("\n")
        entries = []
        for status, path in changed(commit):
            if status == "D":
                entries.append({"path": path, "mode": "100644",
                                "type": "blob", "sha": None})
                print("  D", path)
                continue
            data = base64.b64encode(git_bytes("show", f"{commit}:{path}")).decode()
            sha = gh(f"repos/{repo}/git/blobs", "POST",
                     {"content": data, "encoding": "base64"})["sha"]
            entries.append({"path": path, "mode": "100644",
                            "type": "blob", "sha": sha})
            print(f"  {status} {path}")

        tree = gh(f"repos/{repo}/git/trees", "POST",
                  {"base_tree": head, "tree": entries})["sha"]
        new = gh(f"repos/{repo}/git/commits", "POST",
                 {"message": msg, "tree": tree, "parents": [head]})["sha"]
        gh(f"repos/{repo}/git/refs/heads/{branch}", "PATCH", {"sha": new})
        print(f"  -> {new[:7]} {msg.splitlines()[0]}")
        head = new

    print("完成，远端 head =", head)
    print("本地树:", git("rev-parse", "HEAD^{tree}").strip())
    print("远端树:", gh(f"repos/{repo}/git/commits/{head}")["tree"]["sha"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
