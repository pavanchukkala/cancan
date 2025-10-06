#!/usr/bin/env python3
"""
Play all YouTube embeds on an emapp.cc/watch/... page (inline).
- Does NOT open individual YouTube pages.
- Tries to enable JS API on each iframe and send play commands.
- Uses YT Data API (if YT_API_KEY env var present) to fetch exact durations.
- Otherwise falls back to FALLBACK_PER_VIDEO seconds.
- Waits for the max duration (videos assumed to play concurrently).
"""

import os, time, json, math, re, sys
import urllib.parse as up
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# CONFIG
PAGE_URL = r'http://emapp.cc/watch/%5B%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%2C%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%5D'
FALLBACK_PER_VIDEO = 60         # seconds if no API/duration available
BUFFER_AFTER = 2.0              # extra seconds after max duration
HEADLESS = True
YT_API_KEY = os.getenv("YT_API_KEY")  # optional; set for accurate durations
# --- end config

def log(s): 
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {s}", flush=True)

def parse_ids_from_url(url):
    try:
        dec = up.unquote(url)
        start = dec.index('[')
        end = dec.rindex(']') + 1
        arr = json.loads(dec[start:end])
        ids = [it.get('v') for it in arr if isinstance(it, dict) and it.get('v')]
        return ids
    except Exception:
        # fallback regex (11-char YouTube IDs)
        return re.findall(r'([A-Za-z0-9_-]{11})', url)

def seconds_from_iso8601(d):
    # Parses YouTube duration like 'PT1M23S' -> seconds
    if not d or not d.startswith('P'):
        return None
    # simple parser
    m = re.match(r'P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)', d)
    if not m:
        return None
    h = int(m.group(1) or 0)
    m_ = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h*3600 + m_*60 + s

def fetch_durations_youtube(ids):
    # returns dict id->seconds or empty dict on failure
    if not YT_API_KEY:
        return {}
    try:
        import requests
    except Exception:
        log("requests not installed; cannot call YouTube API.")
        return {}
    if not ids:
        return {}
    # YouTube API limits 50 ids per call
    out = {}
    BATCH = 50
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i+BATCH]
        q = ",".join(batch)
        url = ("https://www.googleapis.com/youtube/v3/videos"
               f"?part=contentDetails&id={q}&key={YT_API_KEY}")
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("items", []):
                vid = item.get("id")
                iso = item.get("contentDetails", {}).get("duration")
                sec = seconds_from_iso8601(iso)
                out[vid] = sec if sec is not None else None
        except Exception as e:
            log(f"YouTube API error: {e}")
            return {}
    return out

def setup_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--mute-audio")
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(60)
    return driver

def enable_jsapi_and_play_all(driver, origin):
    """
    In-page JS:
    - find all <iframe> with youtube embed src
    - append enablejsapi=1&origin=ORIGIN to each src (if not present) and reload it
    - then send the postMessage command to play; also try to click overlays as a fallback
    Returns count of targets found.
    """
    script = """
    (function(origin){
        const iframes = Array.from(document.querySelectorAll('iframe'))
            .filter(f => f.src && f.src.includes('youtube.com'));
        const results = [];
        iframes.forEach((f,idx) => {
            try {
                let src = f.src;
                const u = new URL(src, location.href);
                // ensure embed path uses /embed/VIDEOID if possible (leave as-is otherwise)
                if(!u.searchParams.get('enablejsapi')) {
                    u.searchParams.set('enablejsapi','1');
                }
                if(!u.searchParams.get('origin')) {
                    u.searchParams.set('origin', origin);
                }
                // update src only if changed
                if(u.toString() !== src) {
                    f.src = u.toString();
                }
                // small delay to allow iframe to load
                results.push({idx: idx, status: 'patched', src: f.src});
            } catch(e) {
                results.push({idx: idx, status: 'err', err: String(e)});
            }
        });
        // after a short wait, send play commands
        setTimeout(() => {
            const played = [];
            Array.from(document.querySelectorAll('iframe'))
                 .filter(f => f.src && f.src.includes('youtube.com'))
                 .forEach(f => {
                    try {
                        // postMessage for YT iframe API
                        f.contentWindow.postMessage(JSON.stringify({event:'command',func:'playVideo',args:[]}), '*');
                        played.push({src: f.src, method: 'postMessage'});
                    } catch(e){
                        // fallback: try to click overlay/play button inside parent
                        try {
                            const r = f.getBoundingClientRect();
                            const x = r.left + r.width/2;
                            const y = r.top + r.height/2;
                            const ev = new MouseEvent('click', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y});
                            f.dispatchEvent(ev);
                            played.push({src: f.src, method: 'click-dispatch'});
                        } catch(ee){
                            played.push({src: f.src, method: 'failed', err: String(ee)});
                        }
                    }
                 });
            // expose results
            window._emapp_play_results = {patched: results, played: played, timestamp: Date.now()};
        }, 1200);
        return {found: results.length};
    })(arguments[0]);
    """
    try:
        res = driver.execute_script(script, origin)
        return res.get('found', 0)
    except Exception as e:
        log(f"JS injection/play error: {e}")
        return 0

def main():
    ids = parse_ids_from_url(PAGE_URL)
    if not ids:
        log("No video IDs parsed from URL. Exiting.")
        return 1
    log(f"Parsed {len(ids)} video id(s) from URL (order preserved).")

    # get durations (prefer YT API)
    durations = fetch_durations_youtube(ids)
    if durations:
        log("Fetched durations from YouTube Data API for some/all videos.")
    else:
        log("No YT_API_KEY or API fetch failed — falling back to default per-video duration.")

    # compute max duration
    dur_list = []
    for vid in ids:
        sec = durations.get(vid) if durations else None
        if sec is None:
            sec = FALLBACK_PER_VIDEO
        dur_list.append((vid, int(sec)))
    max_dur = max([d for (_, d) in dur_list]) if dur_list else FALLBACK_PER_VIDEO
    # Digit-by-digit arithmetic example: max_dur + BUFFER_AFTER
    a = str(max_dur).rjust(4,'0')
    b = str(int(BUFFER_AFTER)).rjust(1,'0')
    log(f"Max durations per video (sample): {dur_list[:6]} ...")
    log(f"Wait calculation: max_dur = {max_dur} seconds; buffer = {BUFFER_AFTER}s")

    driver = None
    try:
        driver = setup_driver()
        log(f"Opening page: {PAGE_URL}")
        driver.get(PAGE_URL)
        origin = up.urlparse(driver.current_url).scheme + "://" + up.urlparse(driver.current_url).netloc
        found = enable_jsapi_and_play_all(driver, origin)
        if found == 0:
            log("No youtube iframes found on page (or JS failed). Attempting to play HTML5 <video> tags directly.")
            # try to play any <video> tags inline
            try:
                vcount = driver.execute_script("""
                    var vs = document.querySelectorAll('video');
                    vs.forEach(v => { try { v.play(); } catch(e){} });
                    return vs.length;
                """)
                log(f"HTML5 video tags played: {vcount}")
            except Exception as e:
                log(f"Error trying to play <video> tags: {e}")
        else:
            log(f"Triggered play on {found} youtube iframe(s) (in-page).")

        # Wait for the longest video + buffer
        total_wait = int(math.ceil(max_dur + BUFFER_AFTER))
        # Show arithmetic digit-by-digit: example "0120 + 02 = 0122" (pad to 4 digits)
        pad = max(4, len(str(total_wait)))
        left = str(max_dur).rjust(pad,'0')
        right = str(int(BUFFER_AFTER)).rjust(pad,'0')
        result = str(total_wait).rjust(pad,'0')
        log(f"Calculation: {left} + {right} = {result}")
        log(f"Sleeping {total_wait}s while videos play inline (max duration).")
        time.sleep(total_wait)

        # optional: collect in-page results
        try:
            info = driver.execute_script("return window._emapp_play_results || null;")
            log(f"In-page play results: {info}")
        except Exception:
            pass

        log("Done waiting. Closing browser.")
        driver.quit()
        return 0
    except Exception as e:
        log(f"Fatal: {e}")
        if driver:
            try:
                driver.quit()
            except: pass
        return 2

if __name__ == '__main__':
    sys.exit(main())
