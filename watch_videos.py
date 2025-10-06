#!/usr/bin/env python3
"""
Inline player for emapp.cc/watch/... pages.
Replace the entire contents of your existing watch_videos.py with this file.
Plays YouTube iframes on the page (no navigation to individual YouTube pages).
Optional: set env EMAPP_URL to your full emapp URL (percent-encoded) or edit PAGE_URL below.
Optional: set YT_API_KEY env var to get exact video durations from YouTube Data API.
"""

import os, time, json, math, re, sys
import urllib.parse as up
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
# Either set EMAPP_URL in environment or edit PAGE_URL below.
PAGE_URL = os.getenv("EMAPP_URL") or r'http://emapp.cc/watch/%5B%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%2C%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%5D'
FALLBACK_PER_VIDEO = 60      # seconds when exact duration unavailable
BUFFER_AFTER = 2.0           # seconds to add after max duration
HEADLESS = True
YT_API_KEY = os.getenv("YT_API_KEY")  # optional, for precise durations
# ----------------------------

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
        return re.findall(r'([A-Za-z0-9_-]{11})', url)

def seconds_from_iso8601(d):
    if not d or not d.startswith('P'):
        return None
    m = re.match(r'P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)', d)
    if not m:
        return None
    h = int(m.group(1) or 0); m_ = int(m.group(2) or 0); s = int(m.group(3) or 0)
    return h*3600 + m_*60 + s

def fetch_durations_youtube(ids):
    if not YT_API_KEY:
        return {}
    try:
        import requests
    except Exception:
        log("requests not installed; skipping YouTube API call.")
        return {}
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
    script = """
    (function(origin){
        const iframes = Array.from(document.querySelectorAll('iframe'))
            .filter(f => f.src && f.src.includes('youtube.com'));
        const results = [];
        iframes.forEach((f,idx) => {
            try {
                let src = f.src;
                const u = new URL(src, location.href);
                if(!u.searchParams.get('enablejsapi')) u.searchParams.set('enablejsapi','1');
                if(!u.searchParams.get('origin')) u.searchParams.set('origin', origin);
                if(u.toString() !== src) f.src = u.toString();
                results.push({idx: idx, status: 'patched', src: f.src});
            } catch(e) {
                results.push({idx: idx, status: 'err', err: String(e)});
            }
        });
        setTimeout(() => {
            const played = [];
            Array.from(document.querySelectorAll('iframe'))
                 .filter(f => f.src && f.src.includes('youtube.com'))
                 .forEach(f => {
                    try {
                        f.contentWindow.postMessage(JSON.stringify({event:'command',func:'playVideo',args:[]}), '*');
                        played.push({src: f.src, method: 'postMessage'});
                    } catch(e){
                        try {
                            const r = f.getBoundingClientRect();
                            const x = r.left + r.width/2; const y = r.top + r.height/2;
                            const ev = new MouseEvent('click', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y});
                            f.dispatchEvent(ev);
                            played.push({src: f.src, method: 'click-dispatch'});
                        } catch(ee){
                            played.push({src: f.src, method: 'failed', err: String(ee)});
                        }
                    }
                 });
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
    url = PAGE_URL
    log(f"Using PAGE_URL: {url[:120]}{'...' if len(url)>120 else ''}")
    ids = parse_ids_from_url(url)
    if not ids:
        log("No video IDs parsed from URL. Exiting.")
        return 1
    log(f"Parsed {len(ids)} video id(s).")

    durations = fetch_durations_youtube(ids)
    if durations:
        log("Fetched durations from YouTube Data API.")
    else:
        log("No YT_API_KEY or API failed — using fallback per-video duration.")

    dur_list = []
    for vid in ids:
        sec = durations.get(vid) if durations else None
        if sec is None:
            sec = FALLBACK_PER_VIDEO
        dur_list.append((vid, int(sec)))
    max_dur = max([d for (_, d) in dur_list]) if dur_list else FALLBACK_PER_VIDEO

    pad = max(4, len(str(int(max_dur + BUFFER_AFTER))))
    left = str(int(max_dur)).rjust(pad,'0')
    right = str(int(BUFFER_AFTER)).rjust(pad,'0')
    result = str(int(math.ceil(max_dur + BUFFER_AFTER))).rjust(pad,'0')
    log(f"Calculated wait: {left} + {right} = {result} (seconds)")

    driver = None
    try:
        driver = setup_driver()
        log(f"Opening page: {url}")
        driver.get(url)
        origin = up.urlparse(driver.current_url).scheme + "://" + up.urlparse(driver.current_url).netloc
        found = enable_jsapi_and_play_all(driver, origin)
        if found == 0:
            log("No youtube iframes found or JS failed. Trying to play <video> tags.")
            try:
                vcount = driver.execute_script("var vs=document.querySelectorAll('video'); vs.forEach(v=>{try{v.play()}catch(e){} }); return vs.length;")
                log(f"HTML5 videos attempted to play: {vcount}")
            except Exception as e:
                log(f"Error playing <video> tags: {e}")
        else:
            log(f"Triggered play on {found} youtube iframe(s).")

        total_wait = int(math.ceil(max_dur + BUFFER_AFTER))
        log(f"Sleeping {total_wait}s while videos play inline (max duration).")
        time.sleep(total_wait)

        try:
            info = driver.execute_script("return window._emapp_play_results || null;")
            log(f"In-page play results (sample): {info}")
        except Exception:
            pass

        log("Done. Closing browser.")
        driver.quit()
        return 0
    except Exception as e:
        log(f"Fatal error: {e}")
        if driver:
            try: driver.quit()
            except: pass
        return 2

if __name__ == '__main__':
    sys.exit(main())
