"""Build the 7-slide demo deck (SPEC 8) from the real results and the real screenshots.

Run:  python scripts/build_deck.py      (Windows: .\\.venv\\Scripts\\python.exe scripts\\build_deck.py)
Out:  submission/demo_slides.pptx       (editable in PowerPoint)
      submission/demo_slides.pdf        (only if LibreOffice 'soffice' is installed)
      site/demo_slides.pdf              (copy of the PDF, so it has a public link on the live site)

Every number on the slides is read from site/assets/data/plan.json (written by
`python -m planner.run_plan`) or counted here (number of tests). Screenshots come from
docs/screenshots/ (written by scripts/screenshot.py). Nothing is typed in by hand, so
re-running this script after a change keeps the deck in step with the app.
No NASA logos or insignia are used; map imagery is credited on every slide that shows it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from lxml import etree
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "submission"
LIVE = "https://sonctran.github.io/nasa/"
REPO = "https://github.com/sonctran/nasa"
TEAM = "Marswalk Ops"
MEMBERS = "Son Tran"
EVENT = "NASA Space Apps Challenge 2026"
CHALLENGE = "Interplanetary Survival Guide: Martian Map"
CREDIT = "Map image: HiRISE, NASA/JPL-Caltech/Univ. of Arizona; USGS mosaic (Fergason et al. 2020). Screenshots of the live app."

BG, PANEL, TEXT, MUTED = RGBColor(0x0F, 0x12, 0x16), RGBColor(0x1E, 0x23, 0x2B), RGBColor(0xE8, 0xEA, 0xED), RGBColor(0xA4, 0xAC, 0xB7)
ORANGE, SKY, GO = RGBColor(0xE6, 0x9F, 0x00), RGBColor(0x56, 0xB4, 0xE9), RGBColor(0x3F, 0xBF, 0x8F)
FONT = "Arial"                      # on every Windows PC; LibreOffice swaps in a same-width font for the PDF
W, H = 13.333, 7.5                  # inches, 16:9


def count_tests() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", r.stdout)
    if not m:
        raise SystemExit("could not count the tests:\n" + r.stdout[-400:])
    return int(m.group(1))


def facts() -> dict:
    P = json.loads((ROOT / "site" / "assets" / "data" / "plan.json").read_text(encoding="utf-8"))
    t, mc, sf, V = P["plan"]["totals"], P["montecarlo"], P["safety"], P["validation"]
    alts = {a["id"]: a for a in P["alternatives"]}
    top = P["max_science_plan"]
    drive = next(d for d in V["rover_drives"] if "floor" in d["name"].lower())
    tor = mc["tornado"]["rows"][0]
    return {
        "pts": P["plan"]["value"], "sites": len(P["plan"]["order"]) - 3, "dur": t["duration_min"], "walk": t["walk_min"],
        "work": t["work_min"], "km": t["dist_m"] / 1000, "limit": 60 * P["params_used"]["mission.eva_time_limit"],
        "p": 100 * mc["p_success"], "runs": mc["runs"], "p95": mc["duration_min"]["p95"],
        "top_pts": top["value"], "top_p": 100 * top["p_success"], "solve_ms": P["robust_plan"]["solve_ms"],
        "safe_extra_min": alts["safest"]["duration_min"] - alts["fastest"]["duration_min"],
        "caution_fast": alts["fastest"]["caution_min"], "caution_safe": alts["safest"]["caution_min"],
        "margin_min": sf["walkback"]["min_time_margin_min"], "margin_o2": sf["walkback"]["min_o2_margin_pct_of_capacity"],
        "sep_max": sf["sep"]["max_walk_home_min"], "sep_limit": sf["sep"]["shelter_limit_min"],
        "tor_name": re.sub(r" \(.*\)", "", tor["input"]).replace("Work time: ", "work time at the ").replace("Three Forks sample depot", "depot"),
        "tor_swing": tor["swing_min"],
        "ap_model": V["apollo14_speed_check"]["mean_model_kmh"], "ap_meas": V["apollo14_speed_check"]["mean_measured_kmh"],
        "rover_plan": 100 * drive["options"]["balanced"]["share_of_planned_within_m"]["25"],
        "rover_line": 100 * drive["straight_line"]["share_of_planned_within_m"]["25"],
        "tubes": 10, "checks": len(P["checklist"]["items"]), "go": P["checklist"]["go"],
    }


# ------------------------------------------------------------------------------------ drawing helpers
def text(slide, x, y, w, h, s, size=18, bold=False, color=TEXT, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(size * 0.45)
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color
    return tb


def rect(slide, x, y, w, h, fill, line=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
    sh.shadow.inherit = False
    return sh


def picture(slide, path: Path, x, y, w=None, h=None):
    """Fit the picture inside the box w x h (inches), keeping its shape; returns the drawn size."""
    with Image.open(path) as im:
        ar = im.width / im.height
    if w is not None and h is not None:
        if w / h > ar:
            w = h * ar
        else:
            h = w / ar
    elif w is not None:
        h = w / ar
    else:
        w = h * ar
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    return w, h


def crop(tmp: Path, name: str, box, max_w=1700) -> Path:
    """Crop a screenshot (box in pixels of the 2880 x 1800 file) and shrink it for a small deck."""
    with Image.open(SHOTS / name) as im:
        c = im.crop(box) if box else im.copy()
        if c.width > max_w:
            c = c.resize((max_w, round(c.height * max_w / c.width)), Image.LANCZOS)
        out = tmp / f"{Path(name).stem}_{'_'.join(map(str, box)) if box else 'full'}.jpg"
        c.convert("RGB").save(out, quality=86)
    return out


def base(prs, title: str, n: int, credit: bool = True):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = BG
    rect(s, 0, 0, 0.14, H, ORANGE)
    text(s, 0.6, 0.42, W - 1.2, 1.0, title, size=30, bold=True)
    text(s, 0.6, H - 0.42, W - 2.4, 0.3, CREDIT if credit else "", size=9, color=MUTED)
    text(s, W - 1.6, H - 0.42, 1.0, 0.3, f"{n} / 7", size=10, color=MUTED, align=PP_ALIGN.RIGHT)
    return s


def bullets(slide, x, y, w, items, size=19, gap=0.16, after=None, after_size=15):
    """Short lines with a square orange marker, in ONE text box with a hanging indent, so PowerPoint
    and LibreOffice do the line wrapping and spacing themselves. `after` = a closing muted line."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(H - y - 0.7))
    tf = tb.text_frame
    tf.word_wrap = True
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    ind = Inches(0.3)
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(size * (0.55 + gap))
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(ind))
        pPr.set("indent", str(-ind))
        etree.SubElement(etree.SubElement(pPr, qn("a:buClr")), qn("a:srgbClr")).set("val", "E69F00")
        etree.SubElement(pPr, qn("a:buSzPct")).set("val", "70000")
        etree.SubElement(pPr, qn("a:buFont")).set("typeface", FONT)
        etree.SubElement(pPr, qn("a:buChar")).set("char", "\u25a0")
        r = p.add_run()
        r.text = it
        r.font.size, r.font.name = Pt(size), FONT
        r.font.color.rgb = TEXT
    if after:
        p = tf.add_paragraph()
        p.space_before = Pt(after_size * 0.6)
        r = p.add_run()
        r.text = after
        r.font.size, r.font.name = Pt(after_size), FONT
        r.font.color.rgb = MUTED
    return tb


# ------------------------------------------------------------------------------------ the deck
def build() -> Path:
    F = facts()
    n_tests = count_tests()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    tmp = Path(tempfile.mkdtemp(prefix="deck_"))
    panel = (1960, 152, 2880, 1800)          # the right-hand panel in a 2880 x 1800 screenshot
    mapbox = (0, 152, 1960, 1800)            # the map

    # 1 - title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    picture(s, crop(tmp, "01_first_screen_plan.jpg", (640, 152, 1960, 1800)), W - 6.01, 0, h=H)   # map only, right of the legend
    rect(s, 0, 0, 0.14, H, ORANGE)
    text(s, 0.6, 1.25, 6.2, 1.0, "Marswalk Ops", size=54, bold=True)
    text(s, 0.6, 2.45, 6.1, 1.6, "Plan a six-hour Marswalk in Jezero Crater, and know the odds of getting home on time.", size=24)
    text(s, 0.6, 4.45, 6.1, 1.4, [f"Team {TEAM}: {MEMBERS}", EVENT, f"Challenge: {CHALLENGE}"], size=16, color=MUTED)
    text(s, 0.6, 6.1, 6.1, 0.4, LIVE.replace("https://", ""), size=18, bold=True, color=ORANGE)
    text(s, 0.6, H - 0.42, 6.2, 0.3, "Map image: HiRISE, NASA/JPL-Caltech/Univ. of Arizona; USGS mosaic (Fergason et al. 2020).", size=9, color=MUTED)

    # 2 - the problem
    s = base(prs, "A Marswalk is an operations problem", 2)
    text(s, 0.6, 1.5, 5.6, 1.2, "Two astronauts. Six hours. One oxygen tank each. One shelter.", size=22, bold=True, color=ORANGE)
    bullets(s, 0.6, 2.75, 5.6, ["Where is it safe to walk?", "Which way should we go?", "Which science stops, in what order?",
                                "How likely are we to get home on time?"], size=20,
            after="A map answers the first question. A plan has to answer all four.", after_size=18)
    picture(s, crop(tmp, "08_slope_layer_legend_readout.jpg", (0, 152, 1340, 1800)), 6.75, 1.45, w=6.0, h=5.4)

    # 3 - what you can do
    s = base(prs, "Pick the stops. Get a route, a schedule and a go / no-go.", 3)
    picture(s, crop(tmp, "01_first_screen_plan.jpg", None, max_w=2200), 0.6, 1.4, w=8.3, h=5.3)
    bullets(s, 9.25, 1.5, 3.6, ["Real terrain: 1 m elevation and 25 cm imagery from HiRISE",
                                "Real places: Perseverance sample sites and the Three Forks tube depot",
                                "Change a stop or a rule and the browser re-plans in under a second",
                                f"{F['checks']} safety checks turn red when a rule fails"], size=16)

    # 4 - the optimization
    s = base(prs, "More science or more margin? The tool shows the trade.", 4, credit=False)
    bullets(s, 0.6, 1.5, 7.2, [
        "Stops are chosen by an exact solver: an orienteering problem in Google OR-Tools CP-SAT",
        f"Recommended plan: {F['pts']} science points, home on time in {F['p']:.1f} % of {F['runs']:,} simulated EVAs",
        f"Taking all {F['top_pts']} points drops that to {F['top_p']:.0f} %",
        f"Routes: the safest path costs +{F['safe_extra_min']:.1f} min and cuts time on risky ground from {F['caution_fast']:.1f} to {F['caution_safe']:.1f} min",
    ], size=19, after=f"Solved to proven optimality in {F['solve_ms']:.0f} ms. All results are modeled.")
    picture(s, crop(tmp, "01_first_screen_plan.jpg", (1960, 990, 2880, 1800)), 8.25, 1.5, w=4.5, h=5.2)

    # 5 - risk and safety
    s = base(prs, "Tasks, not walking, decide whether the crew gets home", 5, credit=False)
    bullets(s, 0.6, 1.5, 6.9, [
        f"Work at the stops is {F['work']:.0f} of the {F['dur']:.0f} planned minutes",
        f"Biggest risk driver: {F['tor_name']}, a {F['tor_swing']:.0f} min swing",
        f"Walk-back rule from Apollo, checked every 10 m: tightest margin {F['margin_min']:.0f} min and {F['margin_o2']:.0f} % of the oxygen tank",
        f"Solar-storm rule: never more than {F['sep_max']:.0f} min from shelter (limit {F['sep_limit']:.0f} min, an assumption)",
    ], size=19)
    picture(s, crop(tmp, "04_schedule_montecarlo_tornado.jpg", (1960, 420, 2880, 1800)), 8.0, 1.45, w=4.75, h=5.3)

    # 6 - HUD and live re-plan
    s = base(prs, "Helmet view: when the day changes, the plan changes", 6)
    picture(s, crop(tmp, "13_hud_sep_alert_replay.jpg", None, max_w=2200), 0.6, 1.4, w=8.3, h=5.3)
    bullets(s, 9.25, 1.5, 3.6, ["Plays the walk back as a visor display: next stop, time left, oxygen, way home",
                                "Trigger a solar storm alert, a slow crew or a suit oxygen fault",
                                "A new plan in under a second; every order of the remaining stops is checked",
                                "Event sizes are labelled assumptions"], size=16)

    # 7 - data, checks, honesty
    s = base(prs, "Real NASA data in, checked results out", 7, credit=False)
    text(s, 0.6, 1.45, 5.9, 0.4, "NASA data used", size=20, bold=True, color=ORANGE)
    bullets(s, 0.6, 2.0, 5.9, ["HiRISE elevation (1 m) and image mosaic (25 cm), USGS",
                               "Perseverance traverse, waypoints and raw photos",
                               "Three Forks depot tube records, NASA PDS",
                               "THEMIS infrared, DONKI solar events, Curiosity RAD dose (proxies, labelled)"], size=16, gap=0.0)
    text(s, 6.95, 1.45, 5.8, 0.4, "Checks", size=20, bold=True, color=ORANGE)
    bullets(s, 6.95, 2.0, 5.8, ["Route search equals Dijkstra exactly",
                                f"Browser planner equals the Python planner; {n_tests} automated tests",
                                f"Apollo 14 uphill speed: model {F['ap_model']:.2f} vs measured {F['ap_meas']:.2f} km/h",
                                f"Real rover drive: {F['rover_plan']:.0f} % of our path within 25 m, vs {F['rover_line']:.0f} % for a straight line (a second drive was inconclusive)"],
            size=16, gap=0.0)
    rect(s, 0.6, 5.2, W - 1.2, 1.55, PANEL)
    text(s, 0.85, 5.33, W - 1.7, 1.35, [
        "Use of AI: code, research and drafts were made with Claude Code (Anthropic), directed and reviewed by Son Tran. No AI-generated images.",
        "Limits: walking and suit numbers are lunar, Earth or design values applied to Mars. Every modeled, assumed or proxy value is labelled in the app.",
        "Next: Mars-gravity suit data, rover-assisted EVAs, ESA Mars Climate Database.",
    ], size=13, color=TEXT)

    assert len(prs.slides) <= 7, "the demo may have at most 7 slides"
    OUT.mkdir(exist_ok=True)
    pptx = OUT / "demo_slides.pptx"
    prs.save(pptx)
    shutil.rmtree(tmp, ignore_errors=True)
    return pptx


def to_pdf(pptx: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("LibreOffice not found: open the .pptx in PowerPoint and use File > Export > PDF.")
        return None
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pptx.parent), str(pptx)],
                   check=True, capture_output=True, timeout=180)
    pdf = pptx.with_suffix(".pdf")
    shutil.copyfile(pdf, ROOT / "site" / "demo_slides.pdf")
    return pdf


if __name__ == "__main__":
    f = build()
    print("wrote", f, f"({f.stat().st_size / 1e6:.1f} MB)")
    pdf = to_pdf(f)
    if pdf:
        print("wrote", pdf, f"({pdf.stat().st_size / 1e6:.1f} MB) and site/demo_slides.pdf")
