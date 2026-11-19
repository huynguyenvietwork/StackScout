import pytest

from stackscout import ai


def test_parse_json_bare_fenced_and_with_prose():
    assert ai.parse_json('{"a": 1}') == {"a": 1}
    assert ai.parse_json('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
    assert ai.parse_json('Here you go:\n{"a": [1, 2]}\nDone.') == {"a": [1, 2]}


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2]", "{not json}"])
def test_parse_json_rejects_garbage(text):
    with pytest.raises(ai.AIError):
        ai.parse_json(text)


def test_render_fills_and_rejects_missing_placeholders():
    out = ai.render(
        "revise_profile", profile="{}", correction="thêm Redis", categories="a, b", ecosystems="x"
    )
    assert "thêm Redis" in out and "{{" not in out
    with pytest.raises(ValueError, match="correction"):
        ai.render("revise_profile", profile="{}", categories="a", ecosystems="x")


def test_command_adds_tools_flag_only_for_claude(monkeypatch):
    monkeypatch.delenv("STACKSCOUT_AI_CMD", raising=False)
    assert ai._command("")[-2:] == ["--tools", ""]
    assert ai._command("WebSearch,WebFetch")[-5:] == [
        "--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"]
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "/usr/local/bin/claude -p --tools Read")
    assert ai._command("").count("--tools") == 1
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "gemini -p")
    assert ai._command("") == ["gemini", "-p"]


def test_complete_passes_prompt_on_stdin(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "cat")
    assert ai.complete('{"echo": true}') == '{"echo": true}'
    assert ai.complete_json('{"echo": true}') == {"echo": True}


def test_complete_raises_on_failure(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "false")
    with pytest.raises(ai.AIError, match="exited"):
        ai.complete("hi")
    monkeypatch.setenv("STACKSCOUT_AI_CMD", "definitely-not-a-real-cli-xyz")
    with pytest.raises(ai.AIError, match="not found"):
        ai.complete("hi")


# ---------------------------------------------------------------- API backend

class _Block:
    def __init__(self, type, text=""):
        self.type, self.text = type, text


class _Resp:
    def __init__(self, stop, blocks):
        self.stop_reason, self.content = stop, blocks


def test_backend_choice(monkeypatch):
    monkeypatch.delenv("STACKSCOUT_AI_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai.backend() == "cli"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert ai.backend() == "api"
    monkeypatch.setenv("STACKSCOUT_AI_BACKEND", "cli")
    assert ai.backend() == "cli"


def test_api_backend_resumes_paused_web_research(monkeypatch):
    import anthropic
    monkeypatch.setenv("STACKSCOUT_AI_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    calls = []
    answers = [_Resp("pause_turn", [_Block("server_tool_use")]),
               _Resp("end_turn", [_Block("text", '{"ok": '), _Block("web_search_tool_result"), _Block("text", "true}")])]

    class FakeMessages:
        def create(self, **kw):
            calls.append(kw)
            return answers[len(calls) - 1]

    class FakeClient:
        def __init__(self, **kw):
            self.beta = type("B", (), {"messages": FakeMessages()})()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    assert ai.complete_json("compare", tools="WebSearch,WebFetch") == {"ok": True}
    assert [t["name"] for t in calls[0]["tools"]] == ["web_search", "web_fetch"]
    assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["fallbacks"] == "default"
    assert calls[1]["messages"][1]["role"] == "assistant"  # paused turn sent back, no extra user message

    calls.clear()
    answers[:] = [_Resp("end_turn", [_Block("text", "hi")])]
    assert ai.complete("plain") == "hi" and "tools" not in calls[0]  # text steps get no tools

    answers[:] = [_Resp("refusal", [])]
    calls.clear()
    with pytest.raises(ai.AIError, match="declined"):
        ai.complete("x")
