import json
import os
import subprocess
import sys
from pathlib import Path

from logscope_triage import safe_profile_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(tmp_path, content, *extra):
    log_path = tmp_path / "sample.log"
    log_path.write_text(content, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "logscope_triage",
        str(log_path),
        "--json",
        "--profile",
        "",
        *extra,
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )
    return json.loads(result.stdout)


def test_hilog_emits_versioned_bounded_contract(tmp_path):
    digest = run_cli(
        tmp_path,
        "08-02 12:00:00.001 100 101 E ABCD/Player: open failed id=1\n"
        "08-02 12:00:00.002 100 101 E ABCD/Player: open failed id=2\n",
    )

    assert digest["schema_version"] == "hiagent.log-digest.v1"
    assert digest["claimed_error"].startswith("open failed")
    assert digest["clusters"][0]["count"] == 2
    assert digest["clusters"][0]["representative_line"] == 1
    assert {s["name"] for s in digest["symbols"]} == {"Player"}
    assert digest["key_lines"] == [1]


def test_hisysevent_and_arkts_become_traceable_anchors(tmp_path):
    digest = run_cli(
        tmp_path,
        '{"domain":"AUDIO","name":"START_FAIL","type":"FAULT",'
        '"params":{"FILE":"audio.cpp","LINE":42,"CALLER":"Start","REASON":"busy"}}\n'
        "at Player.start (src/player.ts:17:3)\n",
    )

    anchor = digest["hisysevent_anchors"][0]
    assert anchor["file"] == "audio.cpp"
    assert anchor["source_line"] == "42"
    assert anchor["caller"] == "Start"
    assert digest["fault_frames"][0]["file"] == "src/player.ts"
    assert "AUDIO/START_FAIL" in {s["name"] for s in digest["symbols"]}
    assert digest["claimed_error"] == "AUDIO/START_FAIL"


def test_generic_mode_keeps_plain_logs(tmp_path):
    digest = run_cli(tmp_path, "ERROR request 100 failed\nERROR request 200 failed\n", "--log-format", "generic")

    assert digest["log_format"] == "generic"
    assert digest["clusters"][0]["count"] == 2
    assert digest["hisysevent_anchors"] == []
    assert digest["fault_frames"] == []


def test_default_masking_extracts_parameter_types_without_values(tmp_path):
    digest = run_cli(tmp_path, "connect 10.0.0.1 user=a@example.com id=0xABCD\n", "--log-format", "generic")

    cluster = digest["clusters"][0]
    assert {"IP", "EMAIL", "HEX"}.issubset(set(cluster["parameter_types"]))
    assert "10.0.0.1" not in cluster["template"]
    assert "a@example.com" not in cluster["template"]


def test_windows_arkts_path_is_preserved(tmp_path):
    digest = run_cli(tmp_path, "at Player.start (C:\\src\\player.ts:17:3)\n")

    assert digest["fault_frames"][0]["file"] == "C:\\src\\player.ts"


def test_inference_marks_known_and_unmatched_templates(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"profile_dir": str(tmp_path / "profiles")}), encoding="utf-8")
    common = ("--profile", "baseline", "--config", str(config_path), "--log-format", "generic")
    run_cli(tmp_path, "service ready 1\nservice ready 2\n", *common)

    digest = run_cli(
        tmp_path,
        "service ready 3\ncompletely novel failure\n",
        *common,
        "--drain-mode",
        "inference",
    )

    assert digest["drain_mode"] == "inference"
    assert {cluster["known"] for cluster in digest["clusters"]} == {True, False}


def test_profile_name_cannot_escape_profile_directory():
    assert safe_profile_name("..\\..\\secret/profile") == "secret_profile"
