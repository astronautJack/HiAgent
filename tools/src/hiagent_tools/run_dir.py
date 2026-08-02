"""Create a run artifact directory inside a repository."""

import argparse
import json
from pathlib import Path
import re


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def prepare(repo, run_id):
    if not RUN_ID_RE.fullmatch(run_id or ""):
        return {"ok": False, "path": "", "error": "invalid run_id"}
    root = Path(repo).resolve()
    if not (root / ".git").exists():
        return {"ok": False, "path": "", "error": "repo is not a git working tree"}
    target = root / ".hiagent" / "runs" / run_id
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(target), "error": ""}


def main():
    parser = argparse.ArgumentParser(prog="hiagent-run")
    subparsers = parser.add_subparsers(dest="command")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repo", required=True)
    prepare_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command != "prepare":
        parser.error("choose prepare")
    result = prepare(args.repo, args.run_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
