"""Build the public, read-only demo into docs/index.html (served by GitHub Pages).

    uv run scripts/build_demo.py --repo https://github.com/<you>/stackscout

The page is the real web UI with a static snapshot of one profile's latest
week (default user "demo": a made-up developer). Never point it at a real
person's profile: the snapshot is published as-is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stackscout import config, digest, sources, storage  # noqa: E402
from stackscout import profile as prof  # noqa: E402


def snapshot(user: str, repo: str) -> dict:
    weeks = digest.list_reports(user)
    if not weeks:
        raise SystemExit(f"no report for user {user!r}: run the radar for it first")
    week = weeks[0]
    return {
        "repo": repo,
        "waitlist": f"{repo}/issues/new?template=hosted_waitlist.yml",
        "meta": {
            "categories": [{"id": k, "label": v, "labels": config.category_labels()[k]}
                           for k, v in config.categories().items()],
            "levels": prof.LEVEL_LABEL,
            "languages": list(config.LANGUAGES),
        },
        "profile": storage.load_profile(user),
        "sources": sources.load(user),
        "report": digest.load_report(user, week),
        "comparisons": digest.cached_comparisons(user, week),
        "market": digest.cached_market(user, week),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", default="demo")
    parser.add_argument("--repo", default="https://github.com/huynguyenvietwork/StackScout")
    parser.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    args = parser.parse_args()

    snap = snapshot(args.user, args.repo.rstrip("/"))
    data = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    data = data.replace(" (bản phát hành)", " releases")  # source names stored before the catalog was English
    data = data.replace("</", "<\\/")  # the JSON sits inside a <script> element
    page = (ROOT / "stackscout" / "static" / "index.html").read_text(encoding="utf-8")
    marker = "<script>\n"
    assert page.count(marker) == 1, "expected one inline <script> in index.html"
    page = page.replace(marker, f"<script>window.SS_DEMO = {data};</script>\n{marker}", 1)
    page = page.replace("<title>StackScout</title>", "<title>StackScout demo</title>")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, week {snap['report']['week']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
