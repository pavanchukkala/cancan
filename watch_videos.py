#!/usr/bin/env python3
"""
watch_videos.py — new-from-scratch inline player.

Behavior:
- Open PAGE_URL (or EMAPP_URL env).
- Discover all youtube iframes (recursive including shadow roots).
- Patch iframe src to include enablejsapi=1 & origin.
- Inject parent-side message listener to capture YouTube iframe state messages and HTML5 <video> ended events.
- Simulate a user gesture (CDP mouse click) on each iframe to satisfy autoplay.
- postMessage({event:'command',func:'playVideo',args:[]}) to each iframe.
- Poll status until all tracked items report ended, then exit.

Overwrite your current file with this. Run headful first (HEADLESS=False) to watch it.
"""
import os, time, json, math, urllib.parse as up, sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# -------- CONFIG --------
PAGE_URL = os.getenv("EMAPP_URL") or "http://emapp.cc/watch/%5B%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%2C%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%5D"
HEADLESS = True   # set False to debug visually
POLL_INTERVAL = 2.0
MAX_WAIT_SECONDS = 60 * 60 * 6   # safety cap 6 hours; set to None for infinite (not recommended)
# ------------------------

def log(s):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {s}", flush=True)

def setup_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--mute-audio")
    # enable autoplay policy relaxation (may still require user gesture)
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(120)
    return driver

# Use CDP to simulate a real user click at element center
def cdp_click_element(driver, element):
    try:
        rect = driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return {left:r.left,top:r.top,width:r.width,height:r.height};",
            element
        )
        if not rect:
            return False
        cx = rect['left'] + rect['width'] / 2.0
        cy = rect['top'] + rect['height'] / 2.0
        # dispatch mousePressed and mouseReleased
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mousePressed","button":"left","x":cx,"y":cy,"clickCount":1})
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mouseReleased","button":"left","x":cx,"y":cy,"clickCount":1})
        time.sleep(0.35)
        return True
    except Exception:
        return False

# JS snippet: recursive shadow-root-aware iframe discovery + parent-side watcher injection
INJECT_WATCHER_JS = r"""
(function(origin){
    // Utility: find all iframes even inside shadow roots
    function collectIframes(root){
        var out = [];
        function walk(node){
            try {
                if(!node) return;
                if(node.nodeType === Node.DOCUMENT_NODE || node.nodeType === Node.ELEMENT_NODE) {
                    if(node.tagName === 'IFRAME') out.push(node);
                    // handle shadow root
                    var children = node.children || [];
                    for(var i=0;i<children.length;i++) walk(children[i]);
                    if(node.shadowRoot) walk(node.shadowRoot);
                }
            } catch(e){}
        }
        walk(root || document);
        return out;
    }

    // Ensure a global status object exists
    window._emapp_watch = window._emapp_watch || {players:{}, html_videos:{} , createdAt: Date.now()};

    // attach message listener (idempotent)
    if(!window._emapp_watch._listenerAdded) {
        window.addEventListener('message', function(ev){
            // try to parse what YouTube IFrame API sends
            try {
                var d = ev.data;
                // some players send strings
                if(typeof d === 'string') {
                    try { d = JSON.parse(d); } catch(e){}
                }
                // if it's an object with event/onStateChange
                if(d && typeof d === 'object') {
                    // YouTube IFrame events often have 'event' and 'info' or 'data'
                    var evName = d.event || d.eventName || d.type || null;
                    var info = d.info || d.data || d.infoState || null;
                    // onStateChange -> info 0 means ended; some frames use 'onStateChange' with data 0
                    if(evName === 'onStateChange' || evName === 'stateChange' || (d && d.event === 'onStateChange')) {
                        try {
                            var vid = (d.id || d.playerId || (ev && ev.source && ev.source.location && ev.source.location.href) || null);
                        }catch(e){ vid = null; }
                        // normalize: use source origin + possible embedded videoId from d?
                        // Mark ended if info == 0
                        var ended = false;
                        if(typeof info === 'number' && info === 0) ended = true;
                        if(d && d.info === 0) ended = true;
                        // Best-effort: if message contains 'state' or 'info' keys
                        // Use ev.origin+maybe video id as key; simpler: iterate known players and try match by origin
                        Object.keys(window._emapp_watch.players).forEach(function(k){
                            var rec = window._emapp_watch.players[k];
                            try {
                                if(rec && rec.origin === ev.origin) {
                                    if(ended) rec.ended = true;
                                    rec.lastMsg = d;
                                }
                            } catch(e){}
                        });
                    }
                }
            } catch(e){}
        }, false);
        window._emapp_watch._listenerAdded = true;
    }

    // collect iframe elements
    var frames = collectIframes(document);
    var created = 0;
    frames.forEach(function(f, idx){
        try {
            var src = f.src || f.getAttribute('src') || '';
            // only youtube embeds
            if(!src || src.indexOf('youtube.com') === -1) return;
            // ensure element has id
            if(!f.id) f.id = 'emapp_iframe_' + idx + '_' + Math.floor(Math.random()*100000);
            var id = f.id;
            // ensure enablejsapi & origin present
            try {
                var u = new URL(src, location.href);
                if(!u.searchParams.get('enablejsapi')) u.searchParams.set('enablejsapi','1');
                if(!u.searchParams.get('origin')) u.searchParams.set('origin', origin);
                var newsrc = u.toString();
                if(newsrc !== src) { f.src = newsrc; src = newsrc; }
            } catch(e){}
            // store a record
            window._emapp_watch.players[id] = window._emapp_watch.players[id] || {id:id, src: src, origin: (new URL(src, location.href)).origin, ended:false, lastMsg:null};
            created++;
        } catch(e){}
    });

    // register HTML5 videos
    try {
        var vids = Array.from(document.querySelectorAll('video'));
        vids.forEach(function(v,i){
            try {
                if(!v.id) v.id = 'emapp_htmlvideo_' + i + '_' + Math.floor(Math.random()*100000);
                var id = v.id;
                window._emapp_watch.html_videos[id] = window._emapp_watch.html_videos[id] || {id:id, ended:!!v.ended, duration: v.duration || null, started:false};
                if(!window._emapp_watch.html_videos[id].listenerAdded) {
                    v.addEventListener('play', function(){ window._emapp_watch.html_videos[id].started = true; });
                    v.addEventListener('ended', function(){ window._emapp_watch.html_videos[id].ended = true; });
                    window._emapp_watch.html_videos[id].listenerAdded = true;
                }
            } catch(e){}
        });
    } catch(e){}

    // expose small helpers
    window._emapp_watch.getStatus = function(){
        var out = {players:{}, html_videos:{}, timestamp: Date.now()};
        try {
            Object.keys(window._emapp_watch.players).forEach(function(k){
                var r = window._emapp_watch.players[k];
                out.players[k] = {id:r.id, ended: !!r.ended, src: r.src, origin: r.origin, lastMsg: r.lastMsg || null};
            });
        } catch(e){}
        try {
            Object.keys(window._emapp_watch.html_videos).forEach(function(k){
                var r = window._emapp_watch.html_videos[k];
                out.html_videos[k] = {id:r.id, ended: !!r.ended, duration: r.duration || null, started: !!r.started};
            });
        } catch(e){}
        return out;
    };

    window._emapp_watch.playAll = function(){
        // for each iframe, attempt a postMessage play command
        try {
            Object.keys(window._emapp_watch.players).forEach(function(k){
                try {
                    var rec = window._emapp_watch.players[k];
                    var el = document.getElementById(k);
                    // try to call postMessage to origin
                    var payload = JSON.stringify({event:'command',func:'playVideo',args:[]});
                    try {
                        if(el && el.contentWindow) {
                            el.contentWindow.postMessage(payload, rec.origin || '*');
                        }
                    } catch(e){}
                    // also try fallback target '*' (some browsers)
                    try {
                        if(el && el.contentWindow) el.contentWindow.postMessage(payload, '*');
                    } catch(e){}
                } catch(e){}
            });
            // also try HTML5 video play
            Array.from(document.querySelectorAll('video')).forEach(function(v){
                try { v.play().catch(()=>{}); } catch(e){}
            });
            return true;
        } catch(e){ return false; }
    };

    return {created: created, players: Object.keys(window._emapp_watch.players).length, html_videos: Object.keys(window._emapp_watch.html_videos).length};
})(arguments[0]);
"""

def get_status(driver):
    try:
        res = driver.execute_script("return (window._emapp_watch && window._emapp_watch.getStatus) ? window._emapp_watch.getStatus() : null;")
        return res
    except Exception:
        return None

def play_all_via_page(driver):
    try:
        ok = driver.execute_script("return (window._emapp_watch && window._emapp_watch.playAll) ? window._emapp_watch.playAll() : false;")
        return bool(ok)
    except Exception:
        return False

def find_iframes_elements(driver):
    # Selenium can't easily access shadow DOM recursively; use JS to return list of element ids we recorded
    try:
        ids = driver.execute_script("return Object.keys((window._emapp_watch && window._emapp_watch.players) || {});")
        if not ids:
            return []
        elems = []
        for i in ids:
            try:
                el = driver.find_element("id", i)
                elems.append(el)
            except Exception:
                # element might be inside shadow DOM — try JS to get bounding rect
                try:
                    rect = driver.execute_script("var el=document.getElementById(arguments[0]); if(!el){ return null;} var r = el.getBoundingClientRect(); return {left:r.left, top:r.top, width:r.width, height:r.height};", i)
                    # fallback: ignore if not found
                except Exception:
                    pass
        return elems
    except Exception:
        return []

def main():
    driver = None
    try:
        driver = setup_driver()
        log(f"Opening page: {PAGE_URL}")
        driver.get(PAGE_URL)
        # small initial wait for lazy loads
        time.sleep(1.0)

        origin = up.urlparse(driver.current_url).scheme + "://" + up.urlparse(driver.current_url).netloc
        log(f"Origin resolved: {origin}")

        # inject watcher + discover frames (this will search shadow roots too)
        log("Injecting in-page watcher (shadow-aware) and discovering players/videos...")
        inject_res = driver.execute_script(INJECT_WATCHER_JS, origin)
        log(f"Injection returned: {inject_res}")

        # give the page a moment to patch srcs and load iframes
        time.sleep(1.2)

        # try to bring known iframe elements into view and simulate click (user gesture)
        # find element ids recorded in page
        try:
            recorded_ids = driver.execute_script("return Object.keys((window._emapp_watch && window._emapp_watch.players) || {});")
        except Exception:
            recorded_ids = []

        log(f"Tracked iframe ids count: {len(recorded_ids)}")
        # for each id try to scroll it into view and click via CDP for user gesture
        for idx, elid in enumerate(recorded_ids):
            try:
                # attempt to find element; fallback to JS-based bounding rect click if element not accessible
                try:
                    el = driver.find_element("id", elid)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.25)
                    ok = cdp_click_element(driver, el)
                    log(f"CDP clicked iframe {elid}: {ok}")
                except Exception:
                    # fallback: try to dispatch click via JS on element reference (may fail if shadow)
                    try:
                        driver.execute_script("var el=document.getElementById(arguments[0]); if(el){ el.scrollIntoView({block:'center'}); el.click && el.click(); }", elid)
                        log(f"Fallback JS clicked {elid}")
                    except Exception:
                        log(f"Could not click {elid} (continuing).")
            except Exception:
                pass

        # attempt to start playback via postMessage for all iframes and play() for HTML5
        started = play_all_via_page(driver)
        log(f"playAll invoked: {started}")

        # monitoring loop: wait until every tracked item ended or safety cap
        start = time.time()
        while True:
            status = get_status(driver)
            if not status:
                log("No status available from page yet; retrying...")
                time.sleep(POLL_INTERVAL)
                if MAX_WAIT_SECONDS and (time.time()-start) > MAX_WAIT_SECONDS:
                    log("Max wait reached, aborting.")
                    break
                continue

            players = status.get("players", {}) or {}
            html_videos = status.get("html_videos", {}) or {}

            total = len(players) + len(html_videos)
            ended = 0
            # count ended players
            for k, v in players.items():
                if v.get("ended"):
                    ended += 1
            for k, v in html_videos.items():
                if v.get("ended"):
                    ended += 1

            log(f"Status snapshot: players={len(players)} html_videos={len(html_videos)} total={total} ended={ended}")

            # If there are no tracked items (we couldn't detect), try re-inject once more but avoid loops
            if total == 0:
                log("No tracked players/videos found. Re-attempting discovery once more after a short wait.")
                time.sleep(2.0)
                driver.execute_script(INJECT_WATCHER_JS, origin)
                time.sleep(1.0)
                status = get_status(driver)
                players = (status.get("players", {}) if status else {})
                html_videos = (status.get("html_videos", {}) if status else {})
                total = len(players) + len(html_videos)
                if total == 0:
                    log("Still zero tracked items. This page may block access or use non-standard players. Exiting with code 2.")
                    break

            if ended >= total and total > 0:
                log("All tracked videos reported ended.")
                break

            # safety cap
            if MAX_WAIT_SECONDS and (time.time() - start) > MAX_WAIT_SECONDS:
                log("Reached MAX_WAIT_SECONDS safety cap. Exiting monitor loop.")
                break

            time.sleep(POLL_INTERVAL)

        log("Done monitoring. Cleaning up and closing browser.")
        try:
            driver.quit()
        except:
            pass
        return 0

    except Exception as e:
        log(f"Fatal error: {e}")
        try:
            if driver:
                driver.quit()
        except:
            pass
        return 3

if __name__ == "__main__":
    sys.exit(main())
