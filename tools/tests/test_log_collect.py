import io
import json
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from hiagent_tools.log_collect import collect, _archive_kind, _strip_archive_ext, _is_text


def _write(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def _make_zip(path, members):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def _make_targz(path, members):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tf:
        for name, content in members.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_archive_kind_and_strip():
    assert _archive_kind("a.zip") == "zip"
    assert _archive_kind("b.tar.gz") == "tar"
    assert _archive_kind("c.tgz") == "tar"
    assert _archive_kind("d.gz") == "gz"
    assert _archive_kind("e.7z") == "7z"
    assert _archive_kind("f.rar") == "rar"
    assert _archive_kind("plain.log") is None
    assert _strip_archive_ext("crash.zip") == "crash"
    assert _strip_archive_ext("b.tar.gz") == "b"
    assert _strip_archive_ext("d.log.gz") == "d.log"


def test_single_text_file(tmp_path):
    src = tmp_path / "a.log"
    src.write_text("line1\nline2\n")
    out = tmp_path / "out"
    r = collect(str(src), str(out))
    assert r["ok"]
    assert [f["path"] for f in r["files"]] == ["a.log"]
    assert r["files"][0]["line_count"] == 2


def test_directory_preserves_structure(tmp_path):
    root = tmp_path / "logs"
    _write(root / "a.log", "hello\n")
    _write(root / "nested/b.txt", "world\n")
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    paths = sorted(f["path"] for f in r["files"])
    assert paths == ["a.log", "nested/b.txt"]


def test_zip_extracted_preserving_internal_structure(tmp_path):
    root = tmp_path / "logs"
    _make_zip(root / "crash.zip", {
        "device/hilog.txt": "sig 1\n",
        "device/tombstone.txt": "sigsegv\n",
    })
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    paths = sorted(f["path"] for f in r["files"])
    assert paths == ["crash/device/hilog.txt", "crash/device/tombstone.txt"]


def test_targz_extracted(tmp_path):
    root = tmp_path / "logs"
    _make_targz(root / "bundle.tar.gz", {"x/y.log": "a\nb\n"})
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    assert [f["path"] for f in r["files"]] == ["bundle/x/y.log"]
    assert r["files"][0]["line_count"] == 2


def test_single_gz_decompresses_to_text(tmp_path):
    import gzip
    root = tmp_path / "logs"
    gz = root / "c.log.gz"
    root.mkdir()
    with gzip.open(gz, "wb") as f:
        f.write(b"gz-line1\ngz-line2\n")
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    assert [f["path"] for f in r["files"]] == ["c.log"]
    assert r["files"][0]["line_count"] == 2


def test_nested_archives(tmp_path):
    # a.zip containing inner.tar.gz
    inner_buf = io.BytesIO()
    with tarfile.open(fileobj=inner_buf, mode="w:gz") as tf:
        data = b"deep\n"
        info = tarfile.TarInfo(name="deep.log")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    root = tmp_path / "logs"
    root.mkdir()
    with zipfile.ZipFile(root / "outer.zip", "w") as zf:
        zf.writestr("inner.tar.gz", inner_buf.getvalue())
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    assert [f["path"] for f in r["files"]] == ["outer/inner/deep.log"]


def test_binary_skipped(tmp_path):
    root = tmp_path / "logs"
    root.mkdir()
    (root / "data.bin").write_bytes(b"\x00\x01\x02\x00binary\x00")
    (root / "ok.log").write_text("fine\n")
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    assert [f["path"] for f in r["files"]] == ["ok.log"]
    assert any("data.bin" in s["path"] for s in r["skipped"])


def test_rar_skips_gracefully_when_no_tool(tmp_path, monkeypatch):
    import hiagent_tools.log_collect as mod
    monkeypatch.setattr(mod, "_find_extractor", lambda: None)
    root = tmp_path / "logs"
    root.mkdir()
    (root / "x.rar").write_bytes(b"fake rar")  # not a real rar; just probe the path
    out = tmp_path / "out"
    r = collect(str(root), str(out))
    assert r["ok"]
    assert any("x.rar" in s["path"] for s in r["skipped"])
    assert r["files"] == []


def test_extractor_lookup_prefers_winrar(monkeypatch):
    import hiagent_tools.log_collect as mod
    # 同时有 WinRAR.exe 和 bsdtar 时，优先返回 winrar
    monkeypatch.setattr(mod.shutil, "which", lambda name: {
        "WinRAR.exe": "C:/Program Files/WinRAR/WinRAR.exe",
        "bsdtar": "/usr/bin/bsdtar",
    }.get(name))
    r = mod._find_extractor()
    assert r is not None and r[0] == "winrar"
    # 都没有时返回 None
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(mod.Path, "exists", lambda self: False)
    assert mod._find_extractor() is None


def test_cli_json_output(tmp_path):
    src = tmp_path / "a.log"
    src.write_text("x\n")
    out = tmp_path / "out"
    import subprocess, sys
    proc = subprocess.run(
        [sys.executable, "-m", "hiagent_tools.log_collect", str(src), "-o", str(out), "--json"],
        capture_output=True, text=True)
    # run as module may not be wired; fallback to entry via -c
    if proc.returncode != 0:
        proc = subprocess.run(
            [sys.executable, "-c",
             "from hiagent_tools.log_collect import main; import sys; sys.exit(main())",
             str(src), "-o", str(out), "--json"],
            capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["path"].endswith("out")
