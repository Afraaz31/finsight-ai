"""Keep the live demo awake: Streamlit Community Cloud puts apps to sleep after ~12 hours without visitors.

Run on a schedule by .github/workflows/keep-awake.yml (free on public repos). A plain HTTP request doesn't
count as a visit, so this opens the app in a real (headless) browser. If the app is asleep, it clicks
"Yes, get this app back up!" and waits until FinSight's home page has loaded.

    python scripts/keep_awake.py [url]            (needs: pip install playwright && playwright install chromium)
    BROWSER_CHANNEL=msedge python scripts/keep_awake.py    (locally, use the installed Edge instead)
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.getenv("APP_URL", "https://finsight-ai-pjpdeab37yjpiachcbrnrj.streamlit.app/")
READY_TEXT = "Companies covered"          # on FinSight's home page once the app (and its API) has loaded
WAKE_BUTTON = "Yes, get this app back up"
TIMEOUT_S = 600                           # waking + loading the index and model can take several minutes


def app_text(page) -> str:
    """The app runs inside an iframe on *.streamlit.app; read the page and every frame."""
    texts = []
    for frame in page.frames:
        try:
            texts.append(frame.inner_text("body", timeout=2000))
        except Exception:
            pass
    return "\n".join(texts)


def main(url: str) -> int:
    with sync_playwright() as p:
        channel = os.getenv("BROWSER_CHANNEL")
        browser = p.chromium.launch(headless=True, channel=channel) if channel else p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        clicked = False
        end = time.time() + TIMEOUT_S
        while time.time() < end:
            text = app_text(page)
            if READY_TEXT in text:
                print(f"FinSight is awake{' (woken up)' if clicked else ''}: {url}")
                browser.close()
                return 0
            if not clicked and WAKE_BUTTON in text:
                page.get_by_role("button", name=WAKE_BUTTON).click()
                clicked = True
                print("The app was asleep: clicked the wake-up button, waiting for it to load ...")
            time.sleep(5)
        print(f"FinSight did not finish loading within {TIMEOUT_S // 60} minutes: {url}")
        page.screenshot(path="keep_awake_failure.png", full_page=True)
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else URL))
