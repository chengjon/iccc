#!/usr/bin/env python3
"""
iCCC Hermes Orchestrator — 标准化多 CLI 开发流水线

流水线: 分解 → Worktree → Ruflo Task → 监控 → 审核 → 合并

独立脚本，不依赖 iCCC 包（避免 MongoDB 依赖冲突）。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RUFLO = os.environ.get("RUFLO_URL", "http://localhost:3010/rpc")


# ── Ruflo MCP ──────────────────────────────────


def _rpc(body: dict) -> dict:
    req = urllib.request.Request(
        RUFLO, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def ruflo_init():
    _rpc({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "hermes-orchestrator", "version": "1"}},
    })


def ruflo_task(method: str, **kw) -> dict:
    resp = _rpc({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": f"task_{method}", "arguments": kw},
    })
    text = resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
    return json.loads(text)


# ── Git ────────────────────────────────────────


def wt_add(proj_root: str, branch: str, target: str, base: str = "main") -> dict:
    subprocess.run(["git", "checkout", base], capture_output=True, cwd=proj_root)
    have = subprocess.run(["git", "branch", "--list", branch],
                          capture_output=True, text=True, cwd=proj_root)
    if not have.stdout.strip():
        subprocess.run(["git", "branch", branch, base], capture_output=True, cwd=proj_root)
    path = os.path.abspath(os.path.join(proj_root, "..", target))
    r = subprocess.run(["git", "worktree", "add", path, branch],
                        capture_output=True, text=True, cwd=proj_root)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.strip()}
    return {"ok": True, "path": path, "branch": branch}


def wt_changes(path: str) -> list[str]:
    r = subprocess.run(["git", "diff", "--stat", "main"],
                        capture_output=True, text=True, cwd=path)
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


def merge_branch(proj_root: str, branch: str) -> bool:
    subprocess.run(["git", "checkout", "main"], capture_output=True, cwd=proj_root)
    r = subprocess.run(["git", "merge", "--no-ff", branch],
                        capture_output=True, text=True, cwd=proj_root)
    return r.returncode == 0


# ── 任务分解 (HTN) ────────────────────────────


def decompose(instruction: str) -> list[dict]:
    """将指令分解为子任务列表。实际应由 LLM 生成，此处为示例骨架。"""
    return [
        dict(id="task-001", type="feature",
             desc=f"实现核心功能: {instruction[:40]}",
             branch="feature/core", assigned="claude-code",
             deps=[], wt_dir="wt-core",
             ac=["函数签名正确", "测试覆盖>90%"]),
        dict(id="task-002", type="test",
             desc="编写单元测试",
             branch="feature/test", assigned="opencode",
             deps=["task-001"], wt_dir="wt-test",
             ac=["全部测试通过"]),
        dict(id="task-003", type="review",
             desc="审核代码并合并",
             branch="main", assigned="hermes",
             deps=["task-001", "task-002"], wt_dir="",
             ac=["无回归", "代码规范检查通过"]),
    ]


# ── 主流程 ─────────────────────────────────────


def run(instruction: str, proj_root: str, poll: int = 15):
    print(f"\n{'='*60}")
    print(f" iCCC Hermes Orchestrator")
    print(f" 指令: {instruction}")
    print(f" 项目: {proj_root}")
    print(f"{'='*60}")

    # 1. 分解
    print(f"\n📋 分解任务...")
    tasks = decompose(instruction)
    for t in tasks:
        d = ", ".join(t["deps"]) or "无"
        print(f"  {t['id']}: {t['desc'][:40]} → {t['assigned']}  依赖: {d}")

    # 2. 建 Worktree
    print(f"\n🌳 建 Worktree...")
    wt_map = {}
    for t in tasks:
        if not t["wt_dir"]:
            continue
        r = wt_add(proj_root, t["branch"], t["wt_dir"])
        if r["ok"]:
            wt_map[t["id"]] = r
            # 写 TASK.md
            task_file = Path(r["path"]) / "TASK.md"
            task_file.write_text(
                f"# {t['desc']}\n\n"
                f" Assigned: {t['assigned']} | Branch: {t['branch']}\n\n"
                + "\n".join(f"- [ ] {a}" for a in t["ac"]) + "\n"
            )
            print(f"  ✅ {r['path']}")
        else:
            print(f"  ❌ {r.get('error', '?')}")

    # 3. 分派到 Ruflo
    print(f"\n📤 分派到 Ruflo...")
    ruflo_init()
    tmap = {}
    for t in tasks:
        tid = ruflo_task("create",
                         type=t["type"],
                         description=f"[{t['id']}] {t['desc']}",
                         priority="high" if t["id"] == "task-001" else "medium",
                         tags=[t["assigned"], t["id"]]).get("taskId", "?")
        ruflo_task("assign", taskId=tid, agentIds=[t["assigned"]])
        tmap[t["id"]] = tid
        print(f"  ✅ {t['id']} → ruflo:{tid}  → {t['assigned']}")

    # 4. 监控
    print(f"\n⏳ 监控 (每 {poll}s)...")
    done = set()
    while True:
        s = ruflo_task("summary")
        print(f"  汇总: {s}", end="\r")
        for tid, rid in tmap.items():
            if tid in done:
                continue
            st = ruflo_task("status", taskId=rid).get("status", "")
            if st == "completed":
                done.add(tid)
                print(f"\n  ✅ {tid} 完成! (ruflo:{rid})")
        if len(done) == len(tasks):
            break
        time.sleep(poll)

    # 5. 审核合并
    print(f"\n🔍 审核 & 合并...")
    for tid, wt in wt_map.items():
        changes = wt_changes(wt["path"])
        if changes:
            print(f"\n  [{tid}] 变更:")
            for l in changes[:5]:
                print(f"    {l}")
            ok = merge_branch(proj_root, wt["branch"])
            print(f"  {'✅' if ok else '❌'} 合并 {wt['branch']} → main")

    print(f"\n{'='*60}")
    print("✅ 流水线完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("instruction", help="开发指令")
    a.add_argument("-p", "--project", default=os.getcwd(), help="项目根目录")
    a.add_argument("--poll", type=int, default=15, help="轮询间隔秒数")
    args = a.parse_args()
    run(args.instruction, args.project, args.poll)
