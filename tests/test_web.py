import json
import time

import pytest
from fastapi.testclient import TestClient

from stackscout import ai, storage, web


def skill(name, category="cache", **kw):
    return {"name": name, "category": category, "ecosystem": "any", "level": "intermediate", **kw}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKSCOUT_REPORTS_DIR", str(tmp_path / "reports"))
    return TestClient(web.create_app("web"))


def fake_ai(monkeypatch, payload):
    calls = []

    def complete(prompt, **kw):
        calls.append(prompt)
        return json.dumps(payload)

    monkeypatch.setattr(ai, "complete", complete)
    return calls


def test_index_and_meta(client):
    assert "StackScout" in client.get("/").text
    meta = client.get("/api/meta").json()
    assert meta["categories"][0] == {"id": "language", "label": "Ngôn ngữ lập trình",
                                     "labels": {"vi": "Ngôn ngữ lập trình", "en": "Programming language"}}
    assert meta["languages"] == ["vi", "en", "zh", "ja", "ko"]
    assert meta["levels"]["advanced"] == "thành thạo"


def test_draft_is_not_saved_until_confirmed(client, monkeypatch):
    fake_ai(monkeypatch, {"person": {"role": "Dev"}, "skills": [skill("Redis"), skill("X", category="bogus")]})
    assert client.get("/api/profile").json() == {"profile": None}

    draft = client.post("/api/profile/draft", json={"role": "dev", "skills": "redis, x"}).json()["profile"]
    assert [s["category"] for s in draft["skills"]] == ["cache", "other"]
    assert client.get("/api/profile").json() == {"profile": None}

    saved = client.put("/api/profile", json={"profile": draft}).json()["profile"]
    assert storage.load_profile("web") == saved


def test_draft_requires_skills_answer_with_readable_message(client):
    res = client.post("/api/profile/draft", json={"role": "dev", "skills": ""})
    assert res.status_code == 422
    assert res.json()["detail"].startswith("Invalid request (skills:")  # default language: English
    storage.save_settings("web", {"language": "vi"})
    res = client.post("/api/profile/draft", json={"role": "dev", "skills": ""})
    assert res.json()["detail"].startswith("Dữ liệu gửi lên không hợp lệ (skills:")  # the person's language


def test_long_pasted_stack_is_accepted(client, monkeypatch):
    # Regression: a ~5000-char pasted stack description used to be rejected (422).
    fake_ai(monkeypatch, {"skills": [skill("Redis")]})
    res = client.post("/api/profile/draft", json={"skills": "redis, " * 800})
    assert res.status_code == 200


def test_api_calls_and_browser_errors_are_logged(client, caplog):
    caplog.set_level("INFO", logger="stackscout.web")
    assert client.post("/api/client-log", json={"message": "boom", "detail": "stack"}).status_code == 204
    client.get("/api/profile")
    text = caplog.text
    assert "browser error: boom" in text
    assert "GET /api/profile -> 200" in text


def test_save_rejects_profile_without_skills(client):
    assert client.put("/api/profile", json={"profile": {"person": {"role": "x"}}}).status_code == 422


def test_revise_uses_revise_prompt_when_draft_has_skills(client, monkeypatch):
    calls = fake_ai(monkeypatch, {"person": {"role": "Dev"}, "skills": [skill("Kafka", category="message-queue")]})
    out = client.post("/api/profile/revise", json={
        "draft": {"skills": [skill("Redis")]}, "correction": "thay redis bằng kafka"}).json()["profile"]
    assert "<correction>thay redis bằng kafka</correction>" in calls[0]
    assert [s["name"] for s in out["skills"]] == ["Kafka"]


def test_add_preview_add_and_remove(client, monkeypatch):
    storage.save_profile("web", {"skills": [skill("Redis")]})
    fake_ai(monkeypatch, {"skills": [skill("redis"), skill("Kafka", category="message-queue")]})

    preview = client.post("/api/skills/preview", json={"text": "redis, kafka"}).json()["skills"]
    assert [s["name"] for s in preview] == ["Kafka"]
    assert len(storage.load_profile("web")["skills"]) == 1  # preview does not save

    out = client.post("/api/skills", json={"skills": preview}).json()["profile"]
    assert [s["name"] for s in out["skills"]] == ["Redis", "Kafka"]

    out = client.delete("/api/skills/redis").json()["profile"]
    assert [s["name"] for s in out["skills"]] == ["Kafka"]
    assert client.delete("/api/skills/nope").status_code == 404


def test_skill_endpoints_need_a_profile(client):
    assert client.post("/api/skills", json={"skills": [skill("Redis")]}).status_code == 404


def test_ai_failure_returns_502_with_message(client, monkeypatch):
    def boom(prompt, **kw):
        raise ai.AIError("down")

    monkeypatch.setattr(ai, "complete", boom)
    res = client.post("/api/profile/draft", json={"skills": "redis"})
    assert res.status_code == 502 and "Try again" in res.json()["detail"]


def test_storage_rejects_path_like_ids():
    with pytest.raises(ValueError):
        storage.user_dir("../etc")


# ---------------------------------------------------------------- milestones 2-6 over HTTP

def test_person_and_import_endpoints(client):
    storage.save_profile("web", {"skills": [skill("Redis")]})
    out = client.patch("/api/profile/person", json={"role": "Tech lead", "interests": ["AI agent", "ai agent", " "]})
    assert out.json()["profile"]["person"] == {"role": "Tech lead", "interests": ["AI agent"]}
    assert "category CHỈ được chọn" in client.get("/api/profile/import/prompt").json()["prompt"]

    yml = "skills:\n  - name: redis\n    level: advanced\n  - name: Kafka\n    category: message-queue\n"
    preview = client.post("/api/profile/import/preview", json={"yaml": yml}).json()
    assert [s["name"] for s in preview["added"]] == ["Kafka"]
    assert [(s["name"], s["level"]) for s in preview["profile"]["skills"]] == [("Redis", "advanced"), ("Kafka", "intermediate")]
    assert len(storage.load_profile("web")["skills"]) == 1  # preview does not save
    bad = client.post("/api/profile/import/preview", json={"yaml": "skills: ["})
    assert bad.status_code == 422 and "YAML" in bad.json()["detail"]


def test_sources_endpoints(client, monkeypatch):
    total = len(client.get("/api/sources").json()["sources"])
    toggled = client.patch("/api/sources/lobsters", json={"enabled": False}).json()["sources"]
    assert next(s for s in toggled if s["id"] == "lobsters")["enabled"] is False
    assert len(client.delete("/api/sources/infoq").json()["sources"]) == total - 1
    assert client.delete("/api/sources/nope").status_code == 422
    monkeypatch.setattr(web.sources, "discover", lambda url, client=None: {"name": "Blog", "type": "rss", "url": "https://b.dev/feed"})
    res = client.post("/api/sources", json={"url": "b.dev"}).json()
    assert res["added"]["name"] == "Blog" and len(res["sources"]) == total
    assert len(client.post("/api/sources/reset").json()["sources"]) == total


def test_radar_job_and_reports(client, monkeypatch):
    assert client.post("/api/radar/run").status_code == 404  # no profile yet
    storage.save_profile("web", {"skills": [skill("Redis")]})

    def fake_run(uid, progress):
        progress("Đang gom tin…")
        return {"week": "2026-W47"}

    monkeypatch.setattr(web.digest, "run_radar", fake_run)
    assert client.post("/api/radar/run").status_code == 202
    for _ in range(50):
        status = client.get("/api/radar/status").json()
        if not status["running"]:
            break
        time.sleep(0.02)
    assert status["week"] == "2026-W47" and status["error"] is None
    assert client.get("/api/reports").json() == {"weeks": []}
    assert client.get("/api/reports/2026-W47").status_code == 404


def test_settings_and_compare_endpoints(client, monkeypatch):
    assert client.get("/api/settings").json() == {"language": "en", "chosen": False}
    assert client.put("/api/settings", json={"language": "ja"}).json() == {"language": "ja"}
    assert client.get("/api/settings").json() == {"language": "ja", "chosen": True}
    assert client.put("/api/settings", json={"language": "xx"}).status_code == 422
    assert client.get("/api/compare", params={"week": "2026-W47"}).json() == {"comparisons": {}}

    def fake_compare(uid, week, name, against, force=False):
        if against == "nope":
            raise ValueError("Công cụ này không có trong hồ sơ của bạn.")
        if against == "down":
            raise ai.AIError("down")
        return {"new": name, "current": "Redis", "recommendation": "watch"}

    monkeypatch.setattr(web.digest, "compare_item", fake_compare)
    ok = client.post("/api/compare", json={"week": "2026-W47", "name": "Memurai", "against": "redis"})
    assert ok.json() == {"key": "memurai|redis", "comparison": {"new": "Memurai", "current": "Redis", "recommendation": "watch"}}
    assert client.post("/api/compare", json={"week": "2026-W47", "name": "X", "against": "nope"}).status_code == 422
    assert client.post("/api/compare", json={"week": "2026-W47", "name": "X", "against": "down"}).status_code == 502
    assert client.post("/api/compare", json={"week": "../etc", "name": "X", "against": "y"}).status_code == 422


def test_auto_compare_endpoints(client, monkeypatch):
    assert client.post("/api/compare/auto", json={"week": "2026-W47"}).status_code == 404  # no report
    assert client.post("/api/compare/auto", json={"week": "bad"}).status_code == 422
    storage.save_profile("web", {"skills": [skill("Redis")]})
    report = {"week": "2026-W47", "stack": [{"name": "Valkey", "category": "cache", "rivals": ["Redis"]}]}
    monkeypatch.setattr(web.digest, "load_report", lambda uid, week: report if week == "2026-W47" else None)
    monkeypatch.setattr(web.digest, "cached_comparisons", lambda uid, week: {})
    monkeypatch.setattr(web.digest, "cached_market", lambda uid, week: {})
    seen = []

    def fake_all(uid, week, on_start, on_finish):
        on_start("valkey|redis")
        seen.append(client.get("/api/compare/auto").json())
        on_finish("valkey|redis", "AI chưa xử lý được lúc này.")

    monkeypatch.setattr(web.digest, "compare_all", fake_all)
    first = client.post("/api/compare/auto", json={"week": "2026-W47"}).json()
    assert first["running"] and first["total"] == 1 and first["week"] == "2026-W47"
    for _ in range(50):
        status = client.get("/api/compare/auto").json()
        if not status["running"]:
            break
        time.sleep(0.02)
    assert seen[0]["active"] == ["valkey|redis"]
    assert status == {"running": False, "week": "2026-W47", "total": 1, "done": 1, "active": [],
                      "failed": {"valkey|redis": "AI chưa xử lý được lúc này."}}


def test_notify_endpoints(client, monkeypatch):
    view = client.get("/api/notify").json()
    assert view["schedule"] == {"enabled": True, "frequency": "weekly", "day": "mon", "monthday": 1, "time": "08:00"}
    assert not any(c["enabled"] for c in view["channels"].values()) and view["next"] is None  # nothing set up
    assert view["tz"].startswith("UTC")

    bad = client.put("/api/notify", json={"channels": {"slack": {"url": "https://evil.test/x"}}})
    assert bad.status_code == 422 and "hooks.slack.com" in bad.json()["detail"]
    storage.save_settings("web", {"language": "vi"})
    assert "phải bắt đầu" in client.put("/api/notify", json={"channels": {"slack": {"url": "x"}}}).json()["detail"]
    storage.save_settings("web", {"language": "en"})
    saved = client.put("/api/notify", json={
        "schedule": {"day": "fri", "time": "17:30"},
        "channels": {"slack": {"enabled": True, "url": "https://hooks.slack.com/services/T0/B0/secret123456"},
                     "email": {"enabled": True, "host": "smtp.test", "to": "me@example.test", "password": "hunter2-very-secret"}}}).json()
    assert saved["schedule"]["day"] == "fri" and saved["next"]  # a channel is on: there is a next delivery
    assert saved["channels"]["slack"]["values"]["url"] == {"set": True, "hint": "••••3456"}
    assert "hunter2" not in str(saved) and "secret123456" not in str(saved)  # secrets never go back to the page
    path = storage.user_dir("web") / "notify.yaml"
    assert oct(path.stat().st_mode & 0o777) == "0o600"

    # An empty secret keeps the stored one; null clears it.
    client.put("/api/notify", json={"channels": {"email": {"password": ""}}})
    assert web.notify.resolve("web", "email")["config"]["password"] == "hunter2-very-secret"
    client.put("/api/notify", json={"channels": {"email": {"password": None}}})
    assert web.notify.resolve("web", "email")["config"]["password"] == ""

    sent = []
    monkeypatch.setattr(web.notify, "send_test", lambda u, c, l: sent.append((c, l)))
    log = client.post("/api/notify/test/slack").json()["log"]
    assert sent == [("slack", "en")] and log[0]["channel"] == "slack" and log[0]["ok"]

    def broken(u, c, l):
        raise web.notify.NotifyError("Slack refused the message: 404")
    monkeypatch.setattr(web.notify, "send_test", broken)
    res = client.post("/api/notify/test/slack")
    assert res.status_code == 422 and "404" in res.json()["detail"]
    assert client.get("/api/notify").json()["log"][0]["ok"] is False

    assert client.post("/api/notify/send").status_code == 404  # no digest yet
    monkeypatch.setattr(web.digest, "list_reports", lambda uid: ["2026-W47"])
    monkeypatch.setattr(web.digest, "load_report", lambda uid, week: {"week": week})
    monkeypatch.setattr(web.notify, "send_digest", lambda uid, report, **kw: {"slack": None, "email": "boom"})
    out = client.post("/api/notify/send").json()
    assert out["results"] == {"slack": None, "email": "boom"}

    assert client.post("/api/notify/telegram/chats", json={}).status_code == 422  # no token anywhere
    monkeypatch.setattr(web.notify, "telegram_chats", lambda token: [{"id": "42", "name": "Me", "type": "private"}])
    assert client.post("/api/notify/telegram/chats", json={"token": "1:abc"}).json() == {"chats": [{"id": "42", "name": "Me", "type": "private"}]}
