from hiagent_tools import crg_gate


def status(built, current="abc", files=10):
    return {
        "files": files,
        "built_at_commit": built,
        "current_sha": current,
    }


def test_json_line_ignores_non_json_prefix():
    assert crg_gate._json_line('INFO migration\n{"files": 3}\n') == {"files": 3}


def test_fresh_graph_does_not_mutate(tmp_path, monkeypatch):
    monkeypatch.setattr(crg_gate, "_status", lambda repo: (status("abc"), ""))
    called = []
    monkeypatch.setattr(crg_gate, "_mutation", lambda *args: called.append(args))

    result = crg_gate.gate(str(tmp_path), large_threshold=5000, timeout=30)

    assert result["ok"] is True
    assert result["state"] == "ready"
    assert called == []


def test_stale_graph_uses_incremental_update(tmp_path, monkeypatch):
    statuses = iter([(status("old"), ""), (status("abc"), "")])
    monkeypatch.setattr(crg_gate, "_status", lambda repo: next(statuses))
    operations = []
    monkeypatch.setattr(crg_gate, "_mutation", lambda repo, operation, timeout: (operations.append(operation) or True, "ok"))

    result = crg_gate.gate(str(tmp_path), large_threshold=5000, timeout=30)

    assert result["ok"] is True
    assert operations == ["update"]


def test_large_initial_build_is_detached(tmp_path, monkeypatch):
    monkeypatch.setattr(crg_gate, "_status", lambda repo: (status(None, files=0), ""))
    monkeypatch.setattr(crg_gate, "_tracked_file_count", lambda repo: 6000)
    monkeypatch.setattr(crg_gate, "_start_worker", lambda repo, operation, state, log: 4321)

    result = crg_gate.gate(str(tmp_path), large_threshold=5000, timeout=30)

    assert result["ok"] is False
    assert result["state"] == "building"
    assert "pid=4321" in result["error"]


def test_dirty_worktree_refreshes_even_when_head_is_unchanged(tmp_path, monkeypatch):
    statuses = iter([(status("abc"), ""), (status("abc"), "")])
    monkeypatch.setattr(crg_gate, "_status", lambda repo: next(statuses))
    monkeypatch.setattr(crg_gate, "_has_worktree_changes", lambda repo: True)
    monkeypatch.setattr(crg_gate, "_untracked_warning", lambda repo: "new.py is untracked")
    operations = []
    monkeypatch.setattr(crg_gate, "_mutation", lambda repo, operation, timeout: (operations.append(operation) or True, "ok"))

    result = crg_gate.gate(str(tmp_path), large_threshold=5000, timeout=30)

    assert result["ok"] is True
    assert result["error"] == ""
    assert result["warning"] == "new.py is untracked"
    assert operations == ["update"]


def test_run_returns_actionable_error_when_crg_is_missing(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(crg_gate.subprocess, "run", missing)
    result = crg_gate._run(["code-review-graph", "status"])
    assert result.returncode == 127
    assert "scripts\\install.ps1" in result.stderr


def test_untracked_source_warning_never_stages_files(tmp_path, monkeypatch):
    completed = crg_gate.subprocess.CompletedProcess(
        [], 0, stdout=b"src/new.py\0README.txt\0", stderr=b""
    )
    monkeypatch.setattr(crg_gate.subprocess, "run", lambda *args, **kwargs: completed)

    warning = crg_gate._untracked_warning(str(tmp_path))

    assert "src/new.py" in warning
    assert "README.txt" not in warning
    assert "纳入版本控制" in warning
