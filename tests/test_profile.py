import json

from stackscout import ai, profile as prof


def skill(name, category="orm-data-access", ecosystem="dotnet", level="intermediate", **kw):
    return {"name": name, "category": category, "ecosystem": ecosystem, "level": level, **kw}


def test_clean_coerces_taxonomy_and_drops_junk():
    raw = {
        "person": {"role": "  Backend dev ", "interests": ["AI agent", "ai agent", "", 3]},
        "skills": [
            skill("Entity Framework Core"),
            skill("Bogus", category="made-up", ecosystem="cobol", level="guru"),
            {"name": ""},
            "not a dict",
        ],
        "projects": [{"name": "Shop", "stack": ["Entity Framework Core"]}, {"description": "no name"}],
    }
    p = prof.clean(raw)
    assert p["person"] == {"role": "Backend dev", "interests": ["AI agent"]}
    assert [s["name"] for s in p["skills"]] == ["Entity Framework Core", "Bogus"]
    bogus = p["skills"][1]
    assert (bogus["category"], bogus["ecosystem"], bogus["level"]) == ("other", "any", "intermediate")
    assert set(p) == {"person", "skills"}  # projects are not part of a profile any more
    assert set(p["skills"][0]) == {"name", "category", "ecosystem", "level"}


def test_clean_handles_non_dict_input():
    assert prof.clean(None) == prof.empty_profile()
    assert prof.clean({"skills": "oops", "person": []}) == prof.empty_profile()


def test_clean_merges_duplicate_skills_case_insensitively():
    p = prof.clean({"skills": [
        skill("Docker", category="other", ecosystem="any", level="beginner"),
        skill("docker", category="containers", ecosystem="cloud", level="advanced"),
    ]})
    assert len(p["skills"]) == 1
    d = p["skills"][0]
    assert d["name"] == "Docker"
    assert (d["category"], d["ecosystem"], d["level"]) == ("containers", "cloud", "advanced")


def test_merge_adds_without_overwriting_base():
    base = {
        "person": {"role": "Tech lead", "interests": ["Rust"]},
        "skills": [skill("PostgreSQL", category="database-sql", ecosystem="any", level="advanced")],
    }
    incoming = {
        "person": {"role": "Developer", "interests": ["rust", "AI agent"]},
        "skills": [
            skill("postgresql", category="database-sql", ecosystem="any", level="beginner"),
            skill("Redis", category="cache", ecosystem="any"),
        ],
        "projects": [{"name": "shop", "description": "other text", "stack": ["Redis"]}],
    }
    out = prof.merge(base, incoming)
    assert "projects" not in out
    assert out["person"] == {"role": "Tech lead", "interests": ["Rust", "AI agent"]}
    assert [(s["name"], s["level"]) for s in out["skills"]] == [("PostgreSQL", "advanced"), ("Redis", "intermediate")]
    assert base["skills"][0]["level"] == "advanced" and len(base["skills"]) == 1  # base untouched


def test_remove_and_new_skills():
    p = prof.clean({"skills": [skill("Docker", category="containers"), skill("Redis", category="cache")]})
    cand = prof.clean({"skills": [skill("docker"), skill("Kafka", category="message-queue")]})
    assert [s["name"] for s in prof.new_skills(p, cand)] == ["Kafka"]
    assert prof.remove_skill(p, "DOCKER") is True
    assert prof.remove_skill(p, "nope") is False
    assert [s["name"] for s in p["skills"]] == ["Redis"]


def test_format_profile_groups_by_label_and_escapes_html():
    p = prof.clean({
        "person": {"role": "<dev>", "interests": ["AI"]},
        "skills": [skill("C#", category="language", ecosystem="dotnet", level="advanced"),
                   skill("A&B", category="language")],
        "projects": [{"name": "Shop", "description": "x", "stack": ["C#"]}],
    })
    text = prof.format_profile(p)
    assert "&lt;dev&gt;" in text and "A&amp;B" in text
    assert "<b>Ngôn ngữ lập trình:</b> C# <i>(thành thạo)</i>, A&amp;B <i>(khá)</i>" in text
    assert "Shop" not in text and "AI" in text

    en = prof.format_profile(p, lang="en")
    assert "<b>Role:</b> &lt;dev&gt;" in en
    assert "<b>Programming language:</b> C# <i>(advanced)</i>, A&amp;B <i>(intermediate)</i>" in en
    ja = prof.format_profile(p, lang="ja")
    assert "<b>仕事:</b>" in ja and "C# <i>(上級)</i>" in ja
    assert "Programming language" in ja  # categories: vi label for vi, en label otherwise
    empty = prof.format_profile(prof.empty_profile(), lang="ko")
    assert "(아직 없음)" in empty


def test_build_from_answers_uses_prompt_and_cleans_result(monkeypatch):
    seen = {}

    def fake_complete(prompt, **kw):
        seen["prompt"], seen["kw"] = prompt, kw
        return "```json\n" + json.dumps({
            "person": {"role": "Backend", "interests": []},
            "skills": [skill("Entity Framework Core"), skill("Weird", category="nonsense")],
            "projects": [],
        }) + "\n```"

    monkeypatch.setattr(ai, "complete", fake_complete)
    out = prof.build_from_answers({"role": "backend", "skills": "c#, entity framework"})
    assert "c#, entity framework" in seen["prompt"]
    assert "orm-data-access" in seen["prompt"] and "dotnet" in seen["prompt"]
    assert seen["kw"].get("tools", "") == ""  # no tools for text-only steps
    assert [s["category"] for s in out["skills"]] == ["orm-data-access", "other"]


def test_skills_from_text_returns_only_skills(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda prompt, **kw: json.dumps({
        "person": {"role": "should be dropped", "interests": ["x"]},
        "skills": [skill("Redis", category="cache")],
        "projects": [{"name": "dropped"}],
    }))
    out = prof.skills_from_text("redis")
    assert out["person"] == {"role": "", "interests": []}
    assert "projects" not in out
    assert [s["name"] for s in out["skills"]] == ["Redis"]


# ---------------------------------------------------------------- privacy

def test_profile_keeps_technologies_only():
    p = prof.clean({
        "person": {"role": "Backend dev, xem https://intranet.acme.vn/hr", "interests": ["ops@acme.vn", "Rust"]},
        "skills": [{"name": "Redis", "category": "cache", "evidence": "AcmeAPI/appsettings.json: redis://10.0.3.7:6379",
                    "used_in": ["AcmeAPI", "api.acme.com"]}],
        "projects": [{"name": "AcmeAPI", "description": "Backend DMS cho AcmeCorp, deploy EC2 qua SSH",
                      "stack": ["Redis"]}],
    })
    assert p == {"person": {"role": "Backend dev, xem", "interests": ["Rust"]},
                 "skills": [{"name": "Redis", "category": "cache", "ecosystem": "any", "level": "intermediate"}]}
    for secret in ("AcmeAPI", "AcmeCorp", "EC2", "10.0.3.7", "intranet", "acme"):
        assert secret not in str(p), secret


def test_import_drops_projects_and_evidence():
    yml = """skills:
  - name: Hangfire
    category: background-jobs
    used_in: [AcmeAPI]
    evidence: "AcmeAPI/AcmeAPI.csproj"
projects:
  - name: AcmeAPI
    description: Backend DMS cho AcmeCorp
    stack: [Hangfire]
"""
    out = prof.parse_import(yml)
    assert "AcmeAPI" not in str(out) and "AcmeCorp" not in str(out)
    assert [s["name"] for s in out["skills"]] == ["Hangfire"]


def test_comparison_prompt_gets_technologies_only():
    from stackscout import compare
    reader = compare._reader(prof.clean({"person": {"role": "dev"}, "projects": [{"name": "AcmeAPI"}],
                                         "skills": [{"name": "Redis", "level": "advanced"}]}))
    assert "AcmeAPI" not in reader and "Redis (advanced)" in reader
    assert "Never put anything from it into a web search" in (prof.config.PROMPTS_DIR / "compare.md").read_text()
