"""Screenshot KMC timeline views to verify fixed pipeline field paths.

Creates a new workflow run and waits for the pipeline to complete.
Requires the dev server running on port 8001 with Celery worker.
"""
import json
import sys
import subprocess
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8001"
OPP_ID = 874
TOKEN_FILE = Path.home() / ".commcare-connect" / "token.json"
OUT_DIR = Path(".")


def main():
    token = json.loads(TOKEN_FILE.read_text())["access_token"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(120_000)

        # Console logging
        page.on("console", lambda msg: print(f"  [CONSOLE] {msg.type}: {msg.text}") if "error" in msg.type.lower() else None)

        # Auth
        page.goto(f"{BASE}/labs/test-auth/?token={token}")
        page.wait_for_load_state("networkidle")
        print("Authenticated")

        # Go to workflow list
        page.goto(f"{BASE}/labs/workflow/?opportunity_id={OPP_ID}")
        page.wait_for_load_state("domcontentloaded")

        # Find KMC workflow and create run
        kmc_cards = page.locator('[data-workflow-template="kmc_longitudinal"]')
        kmc_cards.last.wait_for(timeout=10_000)
        print(f"Found {kmc_cards.count()} KMC workflow(s)")

        kmc_card = kmc_cards.last
        kmc_card.get_by_text("Create Run").click()
        page.wait_for_load_state("domcontentloaded")

        # Wait for pipeline — poll for Child List tab (up to 5 min)
        wf_root = page.locator("#workflow-root")
        wf_root.wait_for(timeout=30_000)
        print("Waiting for pipeline to process (up to 5 min)...")

        child_list_btn = wf_root.get_by_role("button", name="Child List")
        child_list_btn.wait_for(timeout=300_000)
        print("Pipeline complete!")

        # Screenshot dashboard
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT_DIR / "kmc_fix_dashboard.png"), full_page=True)
        print("Saved: kmc_fix_dashboard.png")

        # Click "Child List" tab
        child_list_btn.click()
        page.wait_for_timeout(2000)

        # Sort by visits descending
        visits_header = page.locator("th").filter(has_text="Visits")
        visits_header.click()
        page.wait_for_timeout(500)
        visits_header.click()
        page.wait_for_timeout(1000)

        page.screenshot(path=str(OUT_DIR / "kmc_fix_childlist.png"), full_page=False)
        print("Saved: kmc_fix_childlist.png")

        # Click first child (most visits)
        first_row = page.locator("table tbody tr").first
        first_row.click()
        page.wait_for_timeout(3000)

        page.screenshot(path=str(OUT_DIR / "kmc_fix_timeline1.png"), full_page=True)
        print("Saved: kmc_fix_timeline1.png")

        # Scroll to see clinical panel
        page.evaluate("window.scrollTo(0, 600)")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT_DIR / "kmc_fix_timeline2.png"), full_page=False)
        print("Saved: kmc_fix_timeline2.png")

        # Back to child list, click second child
        wf_root.get_by_role("button", name="Child List").click()
        page.wait_for_timeout(1000)
        visits_header = page.locator("th").filter(has_text="Visits")
        visits_header.click()
        page.wait_for_timeout(500)
        visits_header.click()
        page.wait_for_timeout(500)

        second_row = page.locator("table tbody tr").nth(1)
        second_row.click()
        page.wait_for_timeout(3000)

        page.screenshot(path=str(OUT_DIR / "kmc_fix_timeline3.png"), full_page=True)
        print("Saved: kmc_fix_timeline3.png")

        # Cleanup: delete the run we created
        import re
        run_id_match = re.search(r"/run/(\d+)/", page.url)
        if run_id_match:
            run_id = run_id_match.group(1)
            csrf = page.evaluate("document.querySelector('#workflow-root')?.dataset?.csrfToken || ''")
            if csrf:
                page.request.post(
                    f"{BASE}/labs/workflow/api/run/{run_id}/delete/?opportunity_id={OPP_ID}",
                    headers={"X-CSRFToken": csrf},
                )
                print(f"Cleaned up run {run_id}")

        browser.close()
        print("Done!")


if __name__ == "__main__":
    main()
