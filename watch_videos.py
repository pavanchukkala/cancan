#!/usr/bin/env python3
"""
watch_videos.py
- Open the emapp.cc/watch/... URL
- Parse the JSON array of {"v": "...", "t": ...}
- For each video id open YouTube, wait for duration robustly, play and wait
- After all videos, ensure total runtime >= 3600s (1 hour). If less, sleep remaining.
"""

import time
import json
import sys
import math
import re
import urllib.parse as up

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIG ---
# Put your emapp url here (percent-encoded JSON in path). Example from you:
INITIAL_URL = r'http://emapp.cc/watch/%5B%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%2C%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%5D'
# Minimum total runtime required (seconds)
TARGET_TOTAL_SECONDS = 3600
# Fallback per-video wait if duration not available
FALLBACK_WAIT_SECONDS = 60
# Small buffer added after video duration
BUFFER_AFTER = 1.5
# --- end CONFIG ---

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def decode_and_extract_json_from_url(url):
    """Decode percent-encoding and return JSON substring between first '[' and last ']'."""
    decoded = up.unquote(url)
    try:
        start = decoded.index('[')
        end = decoded.rindex(']') + 1
        raw = decoded[start:end]
        return raw
    except ValueError:
        return None

def extract_video_ids_from_string(s):
    """Try to load JSON arr or fallback to regex for youtube ids."""
    if not s:
        return []
    # try JSON
    try:
        arr = json.loads(s)
        ids = [item.get('v') for item in arr if isinstance(item, dict) and item.get('v')]
        return ids
    except Exception:
        pass
    # fallback: find all 11-char youtube ids
    ids = re.findall(r'([A-Za-z0-9_-]{11})', s)
    return ids

def setup_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--mute-audio")
    # try to avoid click-to-play policies
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)
    return driver

def wait_for_numeric_duration(driver, timeout=20):
    """Polls the page for an HTML5 <video> duration that is numeric and > 0."""
    deadline = time.time() + timeout
    try:
        # wait for video element to appear first
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "video")))
    except Exception:
        # video element didn't appear in time
        return None

    while time.time() < deadline:
        try:
            dur = driver.execute_script(
                "const v = document.querySelector('video');"
                "if (!v) return null;"
                "return v.duration;"
            )
        except Exception:
            dur = None

        # dur may be None, NaN, 0, or a positive float
        if isinstance(dur, (int, float)) and not math.isnan(dur) and dur > 0.01:
            return float(dur)
        time.sleep(0.4)
    return None

def open_and_watch(driver, video_id):
    """Open YouTube watch page and attempt to play and wait for duration."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    log(f"Opening YouTube video: {url}")
    try:
        driver.get(url)
    except Exception as e:
        log(f"Page load error for {video_id}: {e}")
        return 0.0

    # Attempt to play using HTML5 video element
    try:
        # Click policy: execute play() via JS
        driver.execute_script("const v = document.querySelector('video'); if (v) { try { v.play(); } catch(e){} }")
    except Exception:
        pass

    duration = wait_for_numeric_duration(driver, timeout=20)
    if duration is not None:
        wait_time = duration + BUFFER_AFTER
        log(f"Video duration: {duration:.1f}s, waiting {wait_time:.1f}s to finish")
        time.sleep(wait_time)
        return float(duration)
    else:
        # fallback
        log(f"No numeric duration detected for {video_id}. Falling back to {FALLBACK_WAIT_SECONDS}s wait.")
        time.sleep(FALLBACK_WAIT_SECONDS)
        return float(FALLBACK_WAIT_SECONDS)

def main():
    driver = None
    total_watched = 0.0
    try:
        driver = setup_driver(headless=True)
        log(f"Visiting initial URL: {INITIAL_URL}")
        try:
            driver.get(INITIAL_URL)
        except Exception as e:
            log(f"Initial page load failed (continuing): {e}")

        # Prefer the actual current URL after redirects (sometimes the browser will decode)
        current = driver.current_url or INITIAL_URL
        decoded_json = decode_and_extract_json_from_url(current)
        ids = extract_video_ids_from_string(decoded_json) if decoded_json else []
        if not ids:
            # try extracting from the raw initial URL string
            decoded_json2 = decode_and_extract_json_from_url(INITIAL_URL)
            ids = extract_video_ids_from_string(decoded_json2) if decoded_json2 else []

        if not ids:
            # last fallback: try to extract a single video id from the url or current_url
            ids = extract_video_ids_from_string(current + " " + INITIAL_URL)

        if not ids:
            log("No video IDs found. Exiting.")
            return 1

        log(f"Found {len(ids)} video id(s). Order preserved.")
        for i, vid in enumerate(ids, 1):
            log(f"Playing {i}/{len(ids)} -> {vid}")
            dur = open_and_watch(driver, vid)
            total_watched += float(dur)
            # small pause between videos
            time.sleep(1.0)

        # Ensure total runtime >= TARGET_TOTAL_SECONDS (1 hour default)
        total = int(math.floor(total_watched))
        # arithmetic (digit-by-digit) example will be printed below
        if total < TARGET_TOTAL_SECONDS:
            remaining = TARGET_TOTAL_SECONDS - total
            # show calculation digits in log
            a = str(TARGET_TOTAL_SECONDS)
            b = str(total).rjust(len(a), "0")
            # e.g. "3600 - 0150 = 3450"
            log(f"Calculation: {a} - {b} = {str(remaining).rjust(len(a),'0')}")
            log(f"Total watched (seconds): {total}. Sleeping remaining {remaining}s to reach {TARGET_TOTAL_SECONDS}s.")
            time.sleep(remaining)
        else:
            log(f"Total watched (seconds): {total}. Target {TARGET_TOTAL_SECONDS}s reached or exceeded; not sleeping extra.")

        log("All videos watched + total-hour enforced. Closing browser.")
        driver.quit()
        return 0

    except Exception as e:
        log(f"Fatal error: {e}")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        return 2

if __name__ == "__main__":
    sys.exit(main())
