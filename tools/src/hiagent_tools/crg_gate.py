"""Reliable CRG freshness gate.

Graph mutations always use the local CLI, never MCP. Large initial builds are
detached so an MCP or agent RPC timeout cannot kill the indexing process.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


STATE_DIR = ".hiagent"
STATE_FILE = "crg-state.json"
LOG_FILE = "crg-build.log"
DEFAULT_LARGE_REPO_THRESHOLD = 5000
DEFAULT_TIMEOUT = 900
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".java", ".kt", ".kts",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".go", ".rs",
    ".cs", ".php", ".rb", ".swift", ".scala", ".vue", ".svelte",
}


def _run(command, timeout=60):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command,
            127,
            stdout="",
            stderr=f"未找到 {command[0]}；请先运行 scripts\\install.ps1，并确认 uv tool bin 已加入 PATH",
        )


def _json_line(text):
    for line in reversed((text or "").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _paths(repo):
    state_dir = Path(repo) / STATE_DIR
    return state_dir, state_dir / STATE_FILE, state_dir / LOG_FILE


def _write_state(path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "hiagent.crg-state.v1", "updated_at": int(time.time()), **values}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_state(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _status(repo):
    result = _run(["code-review-graph", "status", "--repo", repo, "--json"])
    status = _json_line(result.stdout)
    if result.returncode != 0 or status is None:
        return None, (result.stderr or result.stdout or "CRG status failed").strip()
    return status, ""


def _tracked_file_count(repo):
    result = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True)
    if result.returncode != 0:
        return 0
    return len([item for item in result.stdout.split(b"\0") if item])


def _has_worktree_changes(repo):
    result = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain=v1", "-z"],
        capture_output=True,
    )
    return result.returncode == 0 and bool(result.stdout)


def _untracked_source_files(repo, limit=50):
    """Report files CRG's Git-based build/update will not index; never stage them."""
    result = subprocess.run(
        ["git", "-C", repo, "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    files = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        value = raw.decode("utf-8", errors="replace")
        if Path(value).suffix.lower() in SOURCE_SUFFIXES:
            files.append(value)
            if len(files) >= limit:
                break
    return files


def _untracked_warning(repo):
    files = _untracked_source_files(repo)
    if not files:
        return ""
    preview = ", ".join(files[:5])
    remainder = "…" if len(files) > 5 else ""
    return f"CRG 不索引未跟踪源码；本轮请直接读取这些文件，纳入版本控制后再 refresh：{preview}{remainder}"


def _mutation(repo, operation, timeout):
    command = ["code-review-graph", operation, "--repo", repo]
    result = _run(command, timeout=timeout)
    return result.returncode == 0, (result.stderr or result.stdout or "").strip()


def _start_worker(repo, operation, state_path, log_path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    command = [sys.executable, "-m", "hiagent_tools.crg_gate", "worker", "--repo", repo, "--operation", operation]
    detach_options = {"close_fds": True}
    if os.name == "nt":
        detach_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
    else:  # kept for contributor-side tests; the supported product target is Windows
        detach_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        **detach_options,
    )
    log_handle.close()
    _write_state(state_path, state="building", operation=operation, pid=process.pid, error="")
    return process.pid


def gate(repo, large_threshold, timeout):
    repo = str(Path(repo).resolve())
    _, state_path, log_path = _paths(repo)
    state = _read_state(state_path)
    if state.get("state") == "building" and _pid_alive(state.get("pid")):
        return {
            "ok": False,
            "state": "building",
            "error": f"CRG 正在后台{state.get('operation', 'build')}；完成后重试当前 skill",
            "log_path": str(log_path),
        }

    status, status_error = _status(repo)
    if status is None:
        return {"ok": False, "state": "error", "error": status_error, "log_path": str(log_path)}

    current_sha = status.get("current_sha")
    built_sha = status.get("built_at_commit")
    has_graph = bool(status.get("files", 0)) and bool(built_sha)
    worktree_changed = _has_worktree_changes(repo)
    if has_graph and built_sha == current_sha and not worktree_changed:
        _write_state(state_path, state="ready", operation="none", pid=0, error="", built_at_commit=built_sha)
        return {"ok": True, "state": "ready", "error": "", "warning": _untracked_warning(repo), "log_path": str(log_path)}

    operation = "update" if has_graph else "build"
    tracked_files = _tracked_file_count(repo)
    if operation == "build" and tracked_files >= large_threshold:
        pid = _start_worker(repo, operation, state_path, log_path)
        return {
            "ok": False,
            "state": "building",
            "error": f"大仓首次建图已转后台 CLI（pid={pid}，tracked_files={tracked_files}）；完成后重试",
            "log_path": str(log_path),
        }

    try:
        ok, detail = _mutation(repo, operation, timeout)
    except subprocess.TimeoutExpired:
        pid = _start_worker(repo, operation, state_path, log_path)
        return {
            "ok": False,
            "state": "building",
            "error": f"前台 {operation} 超过 {timeout}s，已改由后台 CLI 继续（pid={pid}）；完成后重试",
            "log_path": str(log_path),
        }

    if not ok:
        _write_state(state_path, state="error", operation=operation, pid=0, error=detail[-2000:])
        return {"ok": False, "state": "error", "error": detail[-2000:], "log_path": str(log_path)}

    refreshed, refresh_error = _status(repo)
    ready = bool(refreshed and refreshed.get("files") and refreshed.get("built_at_commit") == refreshed.get("current_sha"))
    _write_state(
        state_path,
        state="ready" if ready else "error",
        operation=operation,
        pid=0,
        error="" if ready else (refresh_error or "CRG mutation completed but graph is not fresh"),
        built_at_commit=(refreshed or {}).get("built_at_commit"),
    )
    return {
        "ok": ready,
        "state": "ready" if ready else "error",
        "error": "" if ready else (refresh_error or "CRG mutation completed but graph is not fresh"),
        "warning": _untracked_warning(repo) if ready else "",
        "log_path": str(log_path),
    }


def refresh(repo, timeout):
    """Refresh tracked working-tree changes before review/impact queries."""
    repo = str(Path(repo).resolve())
    _, state_path, log_path = _paths(repo)
    try:
        ok, detail = _mutation(repo, "update", timeout)
    except subprocess.TimeoutExpired:
        pid = _start_worker(repo, "update", state_path, log_path)
        return {
            "ok": False,
            "state": "building",
            "error": f"CRG update 超过 {timeout}s，已转后台 CLI（pid={pid}）；完成后重试",
            "log_path": str(log_path),
        }
    if not ok:
        return {"ok": False, "state": "error", "error": detail[-2000:], "log_path": str(log_path)}
    return {"ok": True, "state": "ready", "error": "", "warning": _untracked_warning(repo), "log_path": str(log_path)}


def worker(repo, operation):
    _, state_path, _ = _paths(repo)
    _write_state(state_path, state="building", operation=operation, pid=os.getpid(), error="")
    try:
        ok, detail = _mutation(repo, operation, timeout=None)
    except Exception as exc:  # worker must leave a durable failure reason
        _write_state(state_path, state="error", operation=operation, pid=0, error=str(exc))
        return 1
    status, status_error = _status(repo)
    ready = bool(ok and status and status.get("files") and status.get("built_at_commit") == status.get("current_sha"))
    _write_state(
        state_path,
        state="ready" if ready else "error",
        operation=operation,
        pid=0,
        error="" if ready else (status_error or detail[-2000:]),
        built_at_commit=(status or {}).get("built_at_commit"),
    )
    return 0 if ready else 1


def main():
    parser = argparse.ArgumentParser(prog="hiagent-crg")
    subparsers = parser.add_subparsers(dest="command")
    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--repo", required=True)
    gate_parser.add_argument("--large-threshold", type=int, default=int(os.getenv("HIAGENT_CRG_LARGE_THRESHOLD", DEFAULT_LARGE_REPO_THRESHOLD)))
    gate_parser.add_argument("--timeout", type=int, default=int(os.getenv("HIAGENT_CRG_TIMEOUT", DEFAULT_TIMEOUT)))
    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument("--repo", required=True)
    worker_parser.add_argument("--operation", choices=["build", "update"], required=True)
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--repo", required=True)
    refresh_parser.add_argument("--timeout", type=int, default=int(os.getenv("HIAGENT_CRG_TIMEOUT", DEFAULT_TIMEOUT)))
    args = parser.parse_args()

    if args.command == "worker":
        return worker(args.repo, args.operation)
    if args.command == "refresh":
        print(json.dumps(refresh(args.repo, args.timeout), ensure_ascii=False))
        return 0
    if args.command != "gate":
        parser.error("choose gate, refresh, or worker")
    print(json.dumps(gate(args.repo, args.large_threshold, args.timeout), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
