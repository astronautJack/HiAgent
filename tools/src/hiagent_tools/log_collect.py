"""Collect logs from an arbitrary path into a plain-text folder.

任意路径（单文件 / 目录 / 压缩包）→ 一个纯文本日志文件夹，保留原始相对目录结构。
递归解压 .zip .tar .tar.gz .tgz .tar.bz2 .tbz2 .tar.xz .txz .gz .bz2 .xz .7z .rar；
嵌套压缩包递归展开。二进制文件跳过。确定性、无 LLM，输出 JSON 结果（目录路径 + 文件索引 + 跳过项）。
"""

import argparse
import bz2
import gzip
import io
import json
import lzma
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

try:
    import py7zr  # type: ignore
    _HAS_7Z = True
except Exception:
    _HAS_7Z = False

try:
    import rarfile  # type: ignore
    _HAS_RAR = True
except Exception:
    _HAS_RAR = False

TEXT_EXTS = {".log", ".txt", ".hilog", ".tlog", ".out", ".err", ".crash",
             ".tombstone", ".md", ".json", ".xml", ".tsv", ".csv"}
SNIFF_BYTES = 8192
MAX_FILES = 5000
MAX_TOTAL_BYTES = 500 * 1024 * 1024


def _is_binary(path):
    try:
        with open(path, "rb") as f:
            chunk = f.read(SNIFF_BYTES)
        return b"\x00" in chunk
    except OSError:
        return True


def _decodable(path):
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as f:
            f.read(SNIFF_BYTES)
        return True
    except (OSError, UnicodeDecodeError):
        return False


def _is_text(path):
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return not _is_binary(path)
    return not _is_binary(path) and _decodable(path)


def _archive_kind(name):
    """'tar'|'zip'|'gz'|'bz2'|'xz'|'7z'|'rar'|None. tar 优先于单文件压缩（.tar.gz 归 tar）。"""
    n = name.lower()
    if n.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")):
        return "tar"
    if n.endswith(".zip"):
        return "zip"
    if n.endswith(".gz"):
        return "gz"
    if n.endswith(".bz2"):
        return "bz2"
    if n.endswith(".xz"):
        return "xz"
    if n.endswith(".7z"):
        return "7z"
    if n.endswith(".rar"):
        return "rar"
    return None


def _strip_archive_ext(name):
    """压缩包名 → 目录名（去一层或多层压缩扩展名）。"""
    n = name.lower()
    for pair in ((".tar.gz",), (".tgz",), (".tar.bz2",), (".tbz2",),
                 (".tar.xz",), (".txz",), (".tar",), (".zip",),
                 (".7z",), (".rar",)):
        for suf in pair:
            if n.endswith(suf):
                return name[: -len(suf)] or name
    for suf in (".gz", ".bz2", ".xz"):
        if n.endswith(suf):
            return name[: -len(suf)] or name
    return name


def _safe_member(member_name):
    """拒绝对路径与穿越。"""
    if not member_name:
        return None
    if member_name.startswith("/") or member_name.startswith("\\"):
        return None
    parts = Path(member_name).parts
    if ".." in parts:
        return None
    return member_name


def _extract_tar(src, dest):
    with tarfile.open(src) as tf:
        members = [m for m in tf.getmembers() if _safe_member(m.name) is not None]
        try:
            tf.extractall(dest, members=members, filter="data")
        except TypeError:
            tf.extractall(dest, members=members)
    return True, ""


def _extract_zip(src, dest):
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            if _safe_member(info.filename) is None or info.is_dir():
                continue
            zf.extract(info, dest)
    return True, ""


def _extract_7z(src, dest):
    if not _HAS_7Z:
        return False, "py7zr not installed; cannot extract .7z"
    with py7zr.SevenZipFile(src) as sz:
        sz.extractall(dest)
    return True, ""


def _extract_rar(src, dest):
    if not _HAS_RAR:
        return False, "rarfile not installed; cannot extract .rar"
    try:
        with rarfile.RarFile(src) as rf:
            for info in rf.infolist():
                if _safe_member(info.filename) is None or info.is_dir():
                    continue
                rf.extract(info, dest)
        return True, ""
    except Exception as exc:
        return False, f"rar extract failed: {exc}"


def _decompress_single(src, kind, dest):
    """单文件压缩（.gz/.bz2/.xz）→ 解压成 dest 文件。"""
    opener = {"gz": gzip.open, "bz2": bz2.open, "xz": lzma.open}[kind]
    try:
        with opener(src, "rb") as src_f, open(dest, "wb") as out_f:
            shutil.copyfileobj(src_f, out_f)
        return True, ""
    except Exception as exc:
        return False, f"{kind} decompress failed: {exc}"


def _count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _rel(path, root):
    try:
        return str(Path(path).relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _process_dir(src_dir, target_dir, state, inplace=False):
    """遍历 src_dir，按名字映射到 target_dir，保留结构。

    inplace=True 用于已解压到 out 内的目录：文本文件已就位，只记录不复制；
    仅嵌套压缩包继续解压。
    """
    for child in sorted(src_dir.iterdir()):
        if child.is_dir():
            sub = target_dir / child.name
            sub.mkdir(parents=True, exist_ok=True)
            _process_dir(child, sub, state, inplace=inplace)
        elif child.is_file():
            _process_file(child, target_dir, state, inplace=inplace)


def _record(dest, state):
    size = dest.stat().st_size
    state["bytes"] += size
    state["count"] += 1
    state["files"].append({
        "path": _rel(dest, state["out"]),
        "bytes": size,
        "line_count": _count_lines(dest),
    })


def _process_file(src, target_dir, state, inplace=False):
    if state["count"] >= MAX_FILES or state["bytes"] >= MAX_TOTAL_BYTES:
        state["skipped"].append({"path": str(src), "reason": "limit reached"})
        return
    kind = _archive_kind(src.name)

    if kind in ("gz", "bz2", "xz"):
        stem = src.name[: -len(src.suffix)]
        dest = target_dir / stem
        target_dir.mkdir(parents=True, exist_ok=True)
        ok, err = _decompress_single(src, kind, dest)
        if not ok:
            state["skipped"].append({"path": str(src), "reason": err})
            return
        # 解压产物可能是压缩包（.tar）或文本；递归处理
        if _archive_kind(dest.name):
            _process_file(dest, target_dir, state, inplace=False)
            try:
                dest.unlink()
            except OSError:
                pass
        elif _is_text(dest):
            _record(dest, state)
            if inplace:
                try:
                    src.unlink()
                except OSError:
                    pass
        else:
            state["skipped"].append({"path": str(dest), "reason": "binary after decompress"})
            try:
                dest.unlink()
            except OSError:
                pass
        return

    if kind in ("tar", "zip", "7z", "rar"):
        stem = _strip_archive_ext(src.name)
        dest_dir = target_dir / stem
        dest_dir.mkdir(parents=True, exist_ok=True)
        handlers = {"tar": _extract_tar, "zip": _extract_zip,
                    "7z": _extract_7z, "rar": _extract_rar}
        ok, err = handlers[kind](src, dest_dir)
        if not ok:
            state["skipped"].append({"path": str(src), "reason": err})
            return
        # 解压后的内容已就位，原地记录文本、继续解压嵌套压缩包
        _process_dir(dest_dir, dest_dir, state, inplace=True)
        if inplace:
            try:
                src.unlink()
            except OSError:
                pass
        return

    if _is_text(src):
        if inplace:
            # 已在 out 内就位，只记录不复制
            _record(src, state)
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / src.name
            shutil.copyfile(src, dest)
            _record(dest, state)
    else:
        state["skipped"].append({"path": str(src), "reason": "binary or unreadable"})


def collect(input_path, out_dir):
    """任意路径 → out_dir 纯文本日志文件夹（保留结构）。返回结果 dict。"""
    src = Path(input_path)
    if not src.exists():
        return {"ok": False, "path": "", "files": [], "skipped": [],
                "error": f"input not found: {input_path}"}
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    state = {"out": out, "files": [], "skipped": [], "bytes": 0, "count": 0}
    if src.is_dir():
        _process_dir(src, out, state)
    elif src.is_file():
        _process_file(src, out, state)
    else:
        return {"ok": False, "path": "", "files": [], "skipped": [],
                "error": f"unsupported input type: {input_path}"}
    return {"ok": True, "path": str(out), "files": state["files"],
            "skipped": state["skipped"], "count": state["count"],
            "bytes": state["bytes"], "error": ""}


def main():
    ap = argparse.ArgumentParser(
        prog="logscope-collect",
        description="任意路径（文件/目录/压缩包）→ 纯文本日志文件夹，保留目录结构")
    ap.add_argument("input", help="输入路径：单文件、目录或压缩包")
    ap.add_argument("-o", "--out", required=True,
                    help="输出目录（纯文本日志按原结构落地于此）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="输出结构化 JSON")
    args = ap.parse_args()
    result = collect(args.input, args.out)
    if args.as_json or not result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"collected {result['count']} file(s) -> {result['path']}")
        for f in result["files"]:
            print(f"  {f['path']}  ({f['line_count']} lines)")
        for s in result["skipped"]:
            print(f"  skip: {s['path']}  ({s['reason']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
