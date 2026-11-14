"""The README, the submission text and the slides must say what the final build measured.

These tests read the numbers from site/assets/data/plan.json (written by planner.run_plan) and
check that every place that quotes them agrees, so a re-run of the planner cannot leave a stale
number in the story. They also check the Space Apps rules that can be checked by a program.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "site" / "assets" / "data" / "plan.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
PAGE = (ROOT / "submission" / "project_page.md").read_text(encoding="utf-8")
RESUME = (ROOT / "submission" / "resume_bullets.md").read_text(encoding="utf-8")


def headline() -> dict[str, str]:
    """The numbers the story is built on, formatted the way the text writes them."""
    t, mc, sf = PLAN["plan"]["totals"], PLAN["montecarlo"], PLAN["safety"]
    by_value = {c["value"]: c for c in PLAN["candidates"]}
    top = PLAN["max_science_plan"]
    return {
        "science points": f"{PLAN['plan']['value']}",
        "on-time share": f"{100 * mc['p_success']:.1f} %",
        "planned minutes": f"{t['duration_min']:.0f}",
        "distance": f"{t['dist_m'] / 1000:.2f} km",
        "max-science share": f"{100 * top['p_success']:.1f} %",
        "close-call share": f"{100 * by_value[30]['p_success'] + 1e-7:.2f} %",
        "walk-back margin": f"{sf['walkback']['min_time_margin_min']:.0f} min",
        "farthest from shelter": f"{sf['sep']['max_walk_home_min']:.0f} min",
    }


@pytest.mark.parametrize("name,text", [("README.md", README), ("submission/project_page.md", PAGE)])
def test_story_numbers_match_the_plan(name, text):
    missing = [f"{k} = {v}" for k, v in headline().items() if v not in text]
    assert not missing, f"{name} does not quote the measured value(s): {missing}"


def test_resume_bullets_use_measured_numbers():
    h = headline()
    for key in ("on-time share", "max-science share"):
        assert h[key] in RESUME, f"resume bullets do not quote {key} = {h[key]}"


def test_ai_use_is_disclosed_everywhere():
    methods = (ROOT / "site" / "methods.html").read_text(encoding="utf-8")
    for name, text in [("README.md", README), ("methods.html", methods), ("project_page.md", PAGE)]:
        assert "Claude Code" in text, f"{name} must say where AI was used (SPEC rule 4)"
        assert re.search(r"[Nn]o AI-generated images", text), f"{name} must state the AI-image status"


def test_deck_has_at_most_seven_slides_and_names_the_team():
    pptx = pytest.importorskip("pptx")
    f = ROOT / "submission" / "demo_slides.pptx"
    if not f.exists():
        pytest.skip("deck not built yet: python scripts/build_deck.py")
    prs = pptx.Presentation(str(f))
    assert 1 <= len(prs.slides) <= 7, "the Space Apps demo may have at most 7 slides"
    words = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    for must in ("Marswalk Ops", "Son Tran", "Interplanetary Survival Guide: Martian Map", "Claude Code"):
        assert must in words, f"the deck must show: {must}"
    assert headline()["on-time share"] in words, "the deck quotes a stale on-time share: re-run scripts/build_deck.py"


def test_stated_test_count_is_the_real_one(request):
    """'N automated tests' in the README must be the number pytest actually collected."""
    collected = request.session.testscollected
    if collected < 150:
        pytest.skip("only part of the suite is running")
    stated = {int(n) for n in re.findall(r"(\d+) (?:automated|pytest) tests", README + PAGE + RESUME)}
    assert stated == {collected}, f"text says {sorted(stated)} tests, pytest collected {collected}"
