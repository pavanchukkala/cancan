#!/usr/bin/env python3
"""
watch_videos.py — Play ALL YouTube embeds on the emapp page inline and wait until every one ends.
Features:
- Shadow-DOM-aware discovery of iframes
- Patches iframe src with enablejsapi & origin
- Loads YouTube IFrame API and creates YT.Player instances
- Triggers playVideo() and uses CDP click fallback for autoplay
- Computes remaining = duration - currentTime and sleeps the max remaining + buffer
- Final check via getPlayerState(); polite fallback polling if needed
- Uses a unique temporary Chrome profile per run to avoid "user data directory is already in use"
"""

import os
import time
import math
import sys
import shutil
import tempfile
import atexit
import socket
import urllib.parse as up

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG (edit if needed) ----------
PAGE_URL = os.getenv("EMAPP_URL") or "http://emapp.cc/watch/[{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0},{\"v\":\"RTLBD6wiAfw\",\"t\":0}]"
HEADLESS = False           # set False to watch the browser while testing
POLL_INTERVAL = 2.0        # seconds for fallback polling
MAX_INITIAL_WAIT = 180     # wait up to 3 minutes for iframes to appear (no-hurry)
MAX_WAIT_SECONDS = 60*15   # safety cap 15 minutes for this short job
BUFFER_AFTER = 4           # seconds extra after computed remaining
# ------------------------------------------------

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ---------- New robust setup_driver (unique user-data-dir) ----------
def _random_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def setup_driver():
    # create unique temp profile dir for this run
    profile_dir = tempfile.mkdtemp(prefix="selenium_profile_")
    atexit.register(lambda: shutil.rmtree(profile_dir, ignore_errors=True))

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    # Use a fresh profile so concurrent runs won't conflict
    opts.add_argument(f"--user-data-dir={profile_dir}")
    # Stable flags for CI / headless runs
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--mute-audio")
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    # try to set a free remote debugging port to reduce collisions
    try:
        port = _random_free_port()
        opts.add_argument(f"--remote-debugging-port={port}")
    except Exception:
        pass

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(120)
    return driver
# ------------------------------------------------------------------

# CDP click to simulate user gesture
def cdp_click_element(driver, element):
    try:
        dim = driver.execute_script("const r=arguments[0].getBoundingClientRect(); return {left:r.left,top:r.top,width:r.width,height:r.height};", element)
        if not dim:
            return False
        cx = dim['left'] + dim['width']/2.0
        cy = dim['top'] + dim['height']/2.0
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mousePressed","button":"left","x":cx,"y":cy,"clickCount":1})
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mouseReleased","button":"left","x":cx,"y":cy,"clickCount":1})
        time.sleep(0.35)
        return True
    except Exception:
        return False

# discovery + patch (shadow-aware)
INJECT_DISCOVER_AND_PATCH_JS = r"""
(function(origin){
    function walk(node, out){
        try {
            if(!node) return;
            if(node.nodeType === Node.ELEMENT_NODE) {
                if(node.tagName === 'IFRAME') out.push(node);
                var children = node.children || [];
                for(var i=0;i<children.length;i++) walk(children[i], out);
                if(node.shadowRoot) walk(node.shadowRoot, out);
            } else if(node.nodeType === Node.DOCUMENT_NODE) {
                var c = node.children || [];
                for(var i=0;i<c.length;i++) walk(c[i], out);
            }
        } catch(e){}
    }
    var out = [];
    walk(document, out);
    window._emapp_all_players = window._emapp_all_players || {players:{} , html_videos:{}};
    var created = 0;
    out.forEach(function(f, i){
        try {
            var src = f.src || f.getAttribute('src') || '';
            if(!src || src.indexOf('youtube.com') === -1) return;
            if(!f.id) f.id = 'emapp_iframe_' + i + '_' + Math.floor(Math.random()*100000);
            try {
                var u = new URL(src, location.href);
                if(!u.searchParams.get('enablejsapi')) u.searchParams.set('enablejsapi','1');
                if(!u.searchParams.get('origin')) u.searchParams.set('origin', origin);
                var newsrc = u.toString();
                if(newsrc !== src) f.src = newsrc;
                src = newsrc;
            } catch(e){}
            window._emapp_all_players.players[f.id] = {id:f.id, src:src, origin:(new URL(src, location.href)).origin, ended:false};
            created++;
        } catch(e){}
    });
    try {
        var vids = Array.from(document.querySelectorAll('video'));
        vids.forEach(function(v,i){
            try {
                if(!v.id) v.id = 'emapp_htmlvideo_' + i + '_' + Math.floor(Math.random()*100000);
                var uid = v.id;
                window._emapp_all_players.html_videos[uid] = window._emapp_all_players.html_videos[uid] || {id:uid, ended: !!v.ended, duration: v.duration || null, started:false};
                if(!window._emapp_all_players.html_videos[uid].listenerAdded) {
                    v.addEventListener('play', function(){ window._emapp_all_players.html_videos[uid].started = true; });
                    v.addEventListener('ended', function(){ window._emapp_all_players.html_videos[uid].ended = true; });
                    window._emapp_all_players.html_videos[uid].listenerAdded = true;
                }
            } catch(e){}
        });
    } catch(e){}
    return {iframes_found: out.length, players_registered: Object.keys(window._emapp_all_players.players).length, html_videos: Object.keys(window._emapp_all_players.html_videos).length};
})(arguments[0]);
"""

GET_STATUS_JS = r"""
(function(){
    var out = {players:{}, html_videos:{}, ts: Date.now()};
    try {
        var p = window._emapp_all_players && window._emapp_all_players.players || {};
        Object.keys(p).forEach(function(k){
            try {
                out.players[k] = {id:k, src: p[k].src, origin: p[k].origin, ended: !!p[k].ended};
            } catch(e){}
        });
    } catch(e){}
    try {
        var h = window._emapp_all_players && window._emapp_all_players.html_videos || {};
        Object.keys(h).forEach(function(k){
            try { out.html_videos[k] = {id:k, ended: !!h[k].ended, started: !!h[k].started, duration: h[k].duration || null}; } catch(e){}
        });
    } catch(e){}
    return out;
})();
"""

def ensure_yt_iframe_api(driver):
    try:
        driver.execute_script("""
            if(!window._emapp_yt_api_injected){
                var s = document.createElement('script');
                s.src = 'https://www.youtube.com/iframe_api';
                document.head.appendChild(s);
                window._emapp_yt_api_injected = true;
            }
        """)
    except Exception:
        pass
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            ok = driver.execute_script("return (typeof YT !== 'undefined' && YT && YT.Player) ? true : false;")
            if ok:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def create_yt_players(driver):
    CREATE_JS = r"""
    (function(){
        if(typeof YT === 'undefined' || !YT.Player) return {status:'no_api'};
        window._emapp_yt_players = window._emapp_yt_players || {};
        var regs = window._emapp_all_players && window._emapp_all_players.players || {};
        var created = 0;
        Object.keys(regs).forEach(function(k){
            try {
                if(window._emapp_yt_players[k] && window._emapp_yt_players[k].player) return;
                var player = new YT.Player(k, {
                    events: {
                        'onReady': function(e){
                            try { window._emapp_yt_players[k] = window._emapp_yt_players[k] || {}; window._emapp_yt_players[k].player = e.target; } catch(e){}
                        },
                        'onStateChange': function(e){
                            try {
                                var id = (e && e.target && e.target.getIframe) ? e.target.getIframe().id : null;
                                if(!id) id = 'unknown';
                                window._emapp_all_players.players[id] = window._emapp_all_players.players[id] || {};
                                if(e.data === 0) window._emapp_all_players.players[id].ended = true;
                                window._emapp_yt_players[id] = window._emapp_yt_players[id] || {};
                                window._emapp_yt_players[id].lastState = e.data;
                            } catch(e){}
                        }
                    }
                });
                window._emapp_yt_players[k] = {player: player, createdAt: Date.now(), ended:false};
                created++;
            } catch(e){}
        });
        return {created:created, total_reg: Object.keys(regs).length};
    })();
    """
    try:
        res = driver.execute_script(CREATE_JS)
        return res
    except Exception as e:
        return {"error": str(e)}

def invoke_play_on_players(driver):
    try:
        driver.execute_script(r"""
            try {
                Object.keys(window._emapp_yt_players || {}).forEach(function(k){
                    try {
                        var r = window._emapp_yt_players[k];
                        if(r && r.player && r.player.playVideo) {
                            try { r.player.playVideo(); } catch(e){}
                        }
                    } catch(e){}
                });
            } catch(e){}
        """)
    except Exception:
        pass
    try:
        driver.execute_script("Array.from(document.querySelectorAll('video')).forEach(v=>{ try{ v.play().catch(()=>{}); } catch(e){} });")
    except Exception:
        pass

def cdp_click_ids(driver, ids):
    for elid in ids:
        try:
            el = None
            try:
                el = driver.find_element("id", elid)
            except Exception:
                try:
                    driver.execute_script("var e=document.getElementById(arguments[0]); if(e) e.scrollIntoView({block:'center'});", elid)
                except Exception:
                    pass
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.15)
                ok = cdp_click_element(driver, el)
                log(f"CDP click {elid} -> {ok}")
        except Exception:
            pass

def fetch_players_times(driver):
    try:
        return driver.execute_script(r"""
            (function(){
                var out = {};
                try {
                    var map = window._emapp_yt_players || {};
                    Object.keys(map).forEach(function(k){
                        try {
                            var p = map[k].player;
                            var st = (p && p.getPlayerState) ? p.getPlayerState() : null;
                            var dur = (p && p.getDuration) ? (function(){ try { var d = p.getDuration(); return (isNaN(d) ? null : Math.floor(d)); } catch(e){ return null; } })() : null;
                            var cur = (p && p.getCurrentTime) ? (function(){ try { var c = p.getCurrentTime(); return (isNaN(c) ? null : Math.floor(c)); } catch(e){ return null; } })() : null;
                            out[k] = {state: st, duration: dur, current: cur};
                        } catch(e){}
                    });
                } catch(e){}
                return out;
            })();
        """)
    except Exception:
        return {}

def polite_poll_for_end(driver):
    log("Fallback polite polling until page reports all ended (may take long).")
    start = time.time()
    while True:
        status = driver.execute_script(GET_STATUS_JS)
        players = status.get("players", {}) if isinstance(status, dict) else {}
        html_videos = status.get("html_videos", {}) if isinstance(status, dict) else {}
        total = len(players) + len(html_videos)
        ended = sum(1 for v in players.values() if v.get("ended")) + sum(1 for v in html_videos.values() if v.get("ended"))
        log(f"Polite poll: total={total}, ended={ended}")
        if total > 0 and ended >= total:
            log("Polite poll: all ended.")
            return True
        if MAX_WAIT_SECONDS and (time.time()-start) > MAX_WAIT_SECONDS:
            log("Polite poll: reached safety cap. Exiting poll.")
            return False
        time.sleep(POLL_INTERVAL)

def main():
    driver = None
    try:
        driver = setup_driver()
        log(f"Opening page: {PAGE_URL}")
        driver.get(PAGE_URL)

        # wait for iframes/video tags to appear
        log("Waiting for iframes or <video> tags to appear (no hurry).")
        t0 = time.time(); seen = False
        while time.time() - t0 < MAX_INITIAL_WAIT:
            try:
                v = driver.execute_script("return (document.querySelectorAll('iframe[src*=\"youtube.com\"]').length || document.querySelectorAll('video').length) || 0;")
                if v and int(v) > 0:
                    seen = True; break
            except Exception:
                pass
            time.sleep(1.0)
        if not seen:
            log("No iframes/video tags detected after wait. Exiting.")
            driver.quit(); return 2

        origin = up.urlparse(driver.current_url).scheme + "://" + up.urlparse(driver.current_url).netloc
        log(f"Resolved origin: {origin}")

        # discover and patch all iframes
        log("Discovering and patching all youtube iframes (shadow-aware)...")
        disc = driver.execute_script(INJECT_DISCOVER_AND_PATCH_JS, origin)
        log(f"Discovery result: {disc}")

        # ensure YT API
        ok_api = ensure_yt_iframe_api(driver)
        log(f"YouTube IFrame API ready: {ok_api}")

        # create players
        res = create_yt_players(driver)
        log(f"create_yt_players result: {res}")
        time.sleep(1.0)

        # play
        invoke_play_on_players(driver)
        log("Invoked playVideo() on players and attempted HTML5 video play().")

        # collect player ids
        try:
            player_ids = driver.execute_script("return Object.keys(window._emapp_yt_players || {});")
        except Exception:
            player_ids = []
        log(f"YT player instances count: {len(player_ids)}")

        # CDP click fallback
        if player_ids:
            cdp_click_ids(driver, player_ids)
        else:
            log("No YT player instances found for CDP click fallback.")

        time.sleep(1.0)

        # fetch times and compute remaining
        players_info = fetch_players_times(driver)
        if not players_info:
            log("Could not fetch player times. Falling back to polite polling.")
            polite_poll_for_end(driver); driver.quit(); return 0

        remaining_list = []
        for pid, info in players_info.items():
            st = info.get("state"); dur = info.get("duration"); cur = info.get("current")
            if dur is None or cur is None:
                rem = None
            else:
                rem = int(max(0, int(dur) - int(cur)))
            remaining_list.append((pid, st, dur, cur, rem))

        log("Per-player scan:")
        for pid, st, dur, cur, rem in remaining_list:
            log(f"  {pid}: state={st} duration={dur} current={cur} remaining={rem}")

        rem_values = [r for (_,_,_,_,r) in remaining_list if isinstance(r, int)]
        if rem_values:
            max_rem = max(rem_values)
            # show digit-by-digit arithmetic example
            ex = None
            for pid, st, dur, cur, rem in remaining_list:
                if isinstance(rem, int) and rem == max_rem:
                    a = str(int(dur)).rjust(4,'0'); b = str(int(cur)).rjust(4,'0'); c = str(int(rem)).rjust(4,'0')
                    ex = f"{a} - {b} = {c}"; break
            if ex: log(f"Calculation example (duration - current = remaining): {ex}")
            log(f"Example: 0120 + 0004 = 0124 (120s duration + 4s buffer = 124s sleep).")
            wait_for = int(max_rem) + BUFFER_AFTER
            log(f"Sleeping max remaining {max_rem}s + {BUFFER_AFTER}s buffer = {wait_for}s.")
            time.sleep(wait_for)

            # final re-check
            try:
                final_states = driver.execute_script(r"""
                    (function(){
                        var out = {};
                        var map = window._emapp_yt_players || {};
                        Object.keys(map).forEach(function(k){
                            try {
                                var p = map[k].player;
                                var st = (p && p.getPlayerState) ? p.getPlayerState() : null;
                                out[k] = {state:st};
                            } catch(e){}
                        });
                        return out;
                    })();
                """)
                total = len(final_states); ended = sum(1 for v in final_states.values() if v.get('state') == 0)
                log(f"After sleep: players ended={ended}/{total}")
                if total>0 and ended>=total:
                    log("All players ended. Done."); driver.quit(); return 0
                else:
                    log("Not all ended after main sleep; entering polite poll fallback.")
                    polite_poll_for_end(driver); driver.quit(); return 0
            except Exception as e:
                log(f"Final check error: {e}; falling back to polite poll.")
                polite_poll_for_end(driver); driver.quit(); return 0
        else:
            log("No reliable duration/current values; falling back to polite poll.")
            polite_poll_for_end(driver); driver.quit(); return 0

    except Exception as e:
        log(f"Fatal error: {e}")
        try:
            if driver:
                driver.quit()
        except:
            pass
        return 3

if __name__ == '__main__':
    sys.exit(main())
