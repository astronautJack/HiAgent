from hiagent_tools.run_dir import prepare


def test_prepare_stays_inside_git_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    result = prepare(str(tmp_path), "diag-123")
    assert result["ok"] is True
    assert (tmp_path / ".hiagent" / "runs" / "diag-123").is_dir()


def test_prepare_rejects_path_like_run_id(tmp_path):
    (tmp_path / ".git").mkdir()
    result = prepare(str(tmp_path), "..\\outside")
    assert result["ok"] is False
