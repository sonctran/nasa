"""Open the web app in a real browser (Playwright + Chromium), click through every panel, take
screenshots and record every console error, failed request and timing.

Run:  python scripts/screenshot.py            (Windows: .\\.venv\\Scripts\\python.exe scripts\\screenshot.py)
      python scripts/screenshot.py --url https://sonctran.github.io/nasa/ --out docs/screenshots/live
      (tests the deployed site instead of a local server; each run uses a fresh browser profile)
Needs: pip install playwright, then once:  python -m playwright install chromium
Output: docs/screenshots/*.jpg and docs/screenshots/report.json. Exit code 1 if any console error.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / "docs" / "screenshots"
PREINSTALLED = Path("/opt/pw-browsers/chromium")       # cloud container only; ignored elsewhere


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    h = functools.partial(QuietHandler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="test this URL (e.g. the live site) instead of a local server")
    ap.add_argument("--out", type=Path, default=OUT, help="folder for screenshots + report.json")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.url:
        httpd, url = None, args.url if args.url.endswith("/") else args.url + "/"
    else:
        httpd, url = serve()
    rep: dict = {"url": url, "console_errors": [], "console_warnings": [], "page_errors": [], "failed_requests": [],
                 "http_errors": [], "shots": [], "timing_ms": {}, "dom": {}}
    with sync_playwright() as p:
        kw = {"executable_path": str(PREINSTALLED)} if PREINSTALLED.exists() else {}
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        def on_console(m):
            if m.type == "error":
                rep["console_errors"].append(m.text)
            elif m.type == "warning":
                rep["console_warnings"].append(m.text)
        page.on("console", on_console)
        page.on("pageerror", lambda e: rep["page_errors"].append(str(e)))
        page.on("requestfailed", lambda r: rep["failed_requests"].append(f"{r.url} {r.failure}"))
        page.on("response", lambda r: r.status >= 400 and rep["http_errors"].append(f"{r.status} {r.url}"))

        def shot(name: str, target=None):
            f = out / f"{name}.jpg"
            (target or page).screenshot(path=str(f), type="jpeg", quality=72)
            rep["shots"].append(f.name)

        t0 = time.perf_counter()
        page.goto(url)
        page.wait_for_selector(".leaflet-overlay-pane path[stroke='#f0e442']", state="attached", timeout=10000)
        rep["timing_ms"]["first_route_on_map"] = round(1000 * (time.perf_counter() - t0))
        page.wait_for_selector("body[data-ready='1']", timeout=30000)
        rep["timing_ms"]["live_plan_ready"] = round(1000 * (time.perf_counter() - t0))
        page.wait_for_load_state("networkidle")
        rep["timing_ms"]["network_idle"] = round(1000 * (time.perf_counter() - t0))
        page.wait_for_timeout(500)
        rep["dom"]["go_chip"] = page.inner_text("#gochip")
        rep["dom"]["live_result"] = page.inner_text("#live .kpis")
        rep["dom"]["live_status"] = page.inner_text("#live-status")
        shot("01_first_screen_plan")

        page.click("nav.tabs button[data-tab=plan]")
        page.locator("#alts tr[data-alt=safest]").click()
        page.locator("#alts tr[data-alt=fastest]").click()
        page.locator("#pareto").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        shot("02_route_options_pareto")

        page.click("nav.tabs button[data-tab=schedule]")
        page.wait_for_timeout(300)
        shot("03_schedule_gantt_burndown")
        page.locator("#hist").scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        shot("04_schedule_montecarlo_tornado")

        page.click("nav.tabs button[data-tab=stops]")
        page.wait_for_timeout(600)
        shot("05_stop_cards")

        page.click("nav.tabs button[data-tab=safety]")
        page.wait_for_timeout(300)
        rep["dom"]["safety_banner"] = page.inner_text(".gobanner")
        rep["dom"]["checklist"] = page.inner_text(".checklist")
        shot("06_safety_checklist")

        page.click("nav.tabs button[data-tab=checks]")
        page.locator("[data-drive='1']").click()
        page.wait_for_timeout(600)
        shot("07_checks_rover_validation")

        # layers: slope on, legend, cursor readout
        page.click("nav.tabs button[data-tab=plan]")
        page.evaluate("window.__marswalk.map.fitBounds([[900,1000],[2500,2900]])")
        page.check("input[data-r=slope]")
        page.locator("input[data-op=slope]").fill("0.7")
        page.mouse.move(520, 450)
        page.wait_for_timeout(500)
        rep["dom"]["cursor_readout"] = page.inner_text("#readout")
        shot("08_slope_layer_legend_readout")
        page.uncheck("input[data-r=slope]")

        # live re-plan: add Hidden Harbor, a waypoint and a keep-out box; change the slope rule
        t1 = time.perf_counter()
        page.click("[data-add=hidden_harbor]")
        page.wait_for_function("window.__marswalk.res && window.__marswalk.res.order.length === 7", timeout=10000)
        rep["timing_ms"]["replan_add_stop_roundtrip"] = round(1000 * (time.perf_counter() - t1))
        page.wait_for_timeout(300)
        rep["dom"]["after_add_hidden_harbor"] = page.inner_text("#live .kpis")
        rep["dom"]["after_add_go_chip"] = page.inner_text("#gochip")
        shot("09_live_replan_add_stop")
        page.click("#reset")
        page.wait_for_function("window.__marswalk.res && window.__marswalk.res.order.length === 6", timeout=10000)
        page.click("[data-mode=wp]")
        box = page.locator("#map").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.62, box["y"] + box["height"] * 0.35)
        page.wait_for_function("window.__marswalk.res && window.__marswalk.res.order.length === 7", timeout=10000)
        page.keyboard.press("Escape")
        page.locator("#slope").fill("15")
        page.wait_for_timeout(1500)
        rep["dom"]["custom_status"] = page.inner_text("#live-status")
        shot("10_custom_waypoint_slope15")
        page.click("#reset")
        page.wait_for_function("window.__marswalk.res && window.__marswalk.res.order.length === 6 && window.__marswalk.cur.slopeNogo === 20", timeout=10000)
        page.wait_for_timeout(800)

        # HUD
        page.click("#btn-hud")
        page.evaluate("(()=>{const H=window.__marswalk.hud.state; H.T=H.track.end*0.18; window.__marswalk.hud.draw();})()")
        page.wait_for_timeout(300)
        rep["dom"]["hud"] = page.inner_text("#hud-stage")
        shot("11_hud_visor")
        page.click("#hud-ev-slow")
        page.wait_for_selector("#hud-replan:not([hidden])", timeout=5000)
        page.wait_for_timeout(300)
        rep["dom"]["hud_replan_slow"] = page.inner_text("#hud-replan")
        rep["dom"]["replan_ms"] = page.evaluate("window.__marswalk.lastReplan")
        shot("12_hud_live_replan_slow_crew")
        page.click("#hud-play")
        page.wait_for_timeout(1500)
        page.click("#hud-play")
        rep["dom"]["hud_after_play"] = page.inner_text("#hud-clock")
        page.click("#hud-exit")
        # SEP replay from the safety tab
        page.click("nav.tabs button[data-tab=safety]")
        page.click("#sep-replay")
        page.locator("#hud-speed").select_option("600")
        page.wait_for_selector("#hud-replan:not([hidden])", timeout=20000)
        page.wait_for_timeout(500)
        rep["dom"]["hud_replan_sep"] = page.inner_text("#hud-replan")
        shot("13_hud_sep_alert_replay")
        page.keyboard.press("Escape")

        # methods page
        page.goto(url + "methods.html")
        page.wait_for_selector("#md h2", timeout=10000)
        shot("14_methods_page")
        page.click("[data-md='ASSUMPTIONS.md']")
        page.wait_for_timeout(500)
        rep["dom"]["assumptions_tables"] = page.locator("#md table").count()
        page.click("[data-md='DATA_SOURCES.md']")
        page.wait_for_timeout(500)
        rep["dom"]["sources_tables"] = page.locator("#md table").count()

        # tablet size (iPad Air portrait-ish)
        tab = browser.new_context(viewport={"width": 820, "height": 1180}, device_scale_factor=2, has_touch=True)
        tp = tab.new_page()
        tp.on("console", on_console)
        tp.on("pageerror", lambda e: rep["page_errors"].append(str(e)))
        tp.goto(url)
        tp.wait_for_selector("body[data-ready='1']", timeout=30000)
        tp.wait_for_timeout(600)
        tp.screenshot(path=str(out / "15_tablet.jpg"), type="jpeg", quality=72, full_page=False)
        rep["shots"].append("15_tablet.jpg")
        rep["dom"]["tablet_horizontal_overflow_px"] = tp.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        browser.close()
    if httpd:
        httpd.shutdown()
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    bad = rep["console_errors"] + rep["page_errors"] + rep["failed_requests"] + rep["http_errors"]
    print(json.dumps({k: rep[k] for k in ("timing_ms", "console_errors", "page_errors", "failed_requests", "http_errors")}, indent=1))
    print(f"{len(rep['shots'])} screenshots in {out}; {len(bad)} errors")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
