import io
import os
import stat

import pytest

from stackscout import ai, doctor


@pytest.fixture(autouse=True)
def _outside_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "in_docker", lambda: False)
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKSCOUT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("STACKSCOUT_AI_CMD", raising=False)


def test_set_env_replaces_commented_line_appends_new_and_locks_the_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# ---- AI\n# ANTHROPIC_API_KEY=\nOTHER=1\n", encoding="utf-8")
    doctor.set_env(env, "ANTHROPIC_API_KEY", "sk-ant-abc")
    doctor.set_env(env, "STACKSCOUT_AI_BACKEND", "api")
    doctor.set_env(env, "ANTHROPIC_API_KEY", "sk-ant-new")  # second time: replaced, not duplicated
    assert env.read_text(encoding="utf-8") == (
        "# ---- AI\nANTHROPIC_API_KEY=sk-ant-new\nOTHER=1\nSTACKSCOUT_AI_BACKEND=api\n")
    if os.name == "posix":
        assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_ai_check_api_key_missing_wrong_shape_and_present(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_AI_BACKEND", "api")
    assert doctor.check_ai().status == "fail"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "hello")
    assert doctor.check_ai().status == "warn"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    assert doctor.check_ai().status == "ok"


def test_ai_check_online_reports_a_rejected_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    monkeypatch.setattr(doctor, "_api_online_problem", lambda model: "the API key was rejected")
    check = doctor.check_ai(online=True)
    assert check.status == "fail" and "rejected" in check.detail


def test_ai_check_cli_found_or_missing(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "definitely-not-a-real-cli-xyz -p")
    check = doctor.check_ai()
    assert check.status == "fail" and "setup" in check.fix
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "cat")
    assert doctor.check_ai().status == "ok"
    assert doctor.check_ai(online=True).status == "ok"  # `cat` echoes the prompt back


def test_env_file_check(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setenv("STACKSCOUT_AI_BACKEND", "api")
    assert doctor.check_env_file(env).status == "warn"
    monkeypatch.setenv("STACKSCOUT_AI_BACKEND", "cli")
    assert doctor.check_env_file(env).status == "info"  # the claude CLI needs no .env
    env.write_text("X=1\n")
    env.chmod(0o644)
    if os.name == "posix":
        assert "chmod" in doctor.check_env_file(env).fix
    env.chmod(0o600)
    assert doctor.check_env_file(env).status == "ok"


def test_storage_check_writable_and_not(tmp_path, monkeypatch):
    assert doctor.check_storage().status == "ok"
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(blocked / "data"))
    assert doctor.check_storage().status == "fail"


def test_report_exit_code_and_fix_lines():
    out = io.StringIO()
    code = doctor.report([doctor.Check("ok", "Python", "3.12"),
                          doctor.Check("fail", "AI backend", "no key", "run setup")], out)
    assert code == 1 and "→ run setup" in out.getvalue() and "1 problem" in out.getvalue()
    out = io.StringIO()
    assert doctor.report([doctor.Check("ok", "Python", "3.12"), doctor.Check("info", "Profile", "none yet", "x")], out) == 0
    assert "Ready" in out.getvalue() and "127.0.0.1:8000" in out.getvalue()
    out = io.StringIO()
    doctor.report([doctor.Check("warn", "Port", "8000 is in use", "x")], out)
    assert "--port 8001" in out.getvalue() and "127.0.0.1:8001" in out.getvalue()


def test_run_checks_without_profile_is_ready(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "cat")
    checks = {c.name: c for c in doctor.run_checks()}
    assert checks["Profile"].status == "info" and checks["Storage"].status == "ok"
    assert not [c for c in checks.values() if c.status == "fail"]


def test_setup_refuses_without_a_terminal(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert doctor.setup(tmp_path / ".env") == 1
    assert "own terminal" in capsys.readouterr().out
    assert not (tmp_path / ".env").exists()


def test_api_usage_is_counted(monkeypatch):
    class Usage:
        input_tokens, output_tokens = 1200, 300
        cache_read_input_tokens = cache_creation_input_tokens = None
        server_tool_use = type("S", (), {"web_search_requests": 2})()

    before = dict(ai.USAGE)
    ai._record_usage(type("R", (), {"usage": Usage()})())
    ai._record_usage(object())  # no usage attribute: ignored
    assert ai.USAGE["calls"] - before["calls"] == 1
    assert ai.USAGE["input_tokens"] - before["input_tokens"] == 1200
    assert ai.USAGE["web_searches"] - before["web_searches"] == 2
