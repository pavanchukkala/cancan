#!/usr/bin/env python3
"""
watch_videos.py — Inline player that waits for all videos to finish.

Behavior:
- Open the emapp page (EMAPP_URL or PAGE_URL).
- Wait for iframes/video tags to appear (no hurry).
- Inject YouTube IFrame API, create YT.Player instances for each YouTube iframe.
- Attach 'onStateChange' handlers to track ended/duration.
- Attach 'ended' handlers for any HTML5 <video> tags.
- Start playback for all players/videos in-place.
- Poll until every tracked player/video has ended, then close the browser.

Overwrite your previous watch_videos.py with this file.
"""
import os
import time
import json
import math
import urllib.parse as up
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# -------- CONFIG --------
PAGE_URL = os.getenv("EMAPP_URL") or r'http://emapp.cc/watch/%5B%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%2C%7B%22v%22%3A%22VaWr_jHqcuE%22%2C%22t%22%3A0%7D%5D'
HEADLESS = True            # set False to watch the browser
WAIT_IFRAMES_TIMEOUT = 300 # seconds to wait for iframes/video tags to appear (no-hurry)
POLL_INTERVAL = 3         # seconds between status polls
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
    # try to reduce autoplay friction
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(120)
    return driver

# JavaScript to inject: create players and start playback. It returns immediately.
INJECT_JS_SETUP_PLAYERS = r"""
(function(origin){
    try {
        window._emapp_players = window._emapp_players || {};
        window._emapp_html_videos = window._emapp_html_videos || {};
        window._emapp_player_ready = window._emapp_player_ready || false;
        window._emapp_players_created_at = window._emapp_players_created_at || Date.now();

        // patch iframe src to include enablejsapi & origin
        var iframes = Array.from(document.querySelectorAll('iframe')).filter(f => f.src && f.src.match(/youtube\.com/));
        iframes.forEach(function(f, idx){
            try {
                var u = new URL(f.src, location.href);
                if(!u.searchParams.get('enablejsapi')) u.searchParams.set('enablejsapi','1');
                if(!u.searchParams.get('origin')) u.searchParams.set('origin', origin);
                // add id if missing
                if(!f.id) f.id = 'emapp_iframe_' + idx + '_' + Math.floor(Math.random()*100000);
                var newsrc = u.toString();
                if(newsrc !== f.src) f.src = newsrc;
            } catch(e){}
        });

        // track HTML5 <video> tags
        var vids = Array.from(document.querySelectorAll('video'));
        vids.forEach(function(v, i){
            try {
                var uid = v.id || ('emapp_htmlvideo_' + i + '_' + Math.floor(Math.random()*100000));
                v.id = uid;
                window._emapp_html_videos[uid] = window._emapp_html_videos[uid] || {ended: v.ended===true, duration: v.duration||null, started: false};
                if(!window._emapp_html_videos[uid].listenerAdded) {
                    v.addEventListener('play', function(){ window._emapp_html_videos[uid].started = true; });
                    v.addEventListener('ended', function(){ window._emapp_html_videos[uid].ended = true; });
                    window._emapp_html_videos[uid].listenerAdded = true;
                }
            } catch(e){}
        });

        // inject YouTube API if there are youtube iframes and API not loaded
        var needsApi = iframes.length > 0 && (typeof YT === 'undefined' || !window._emapp_yt_api_ready);
        if(needsApi && !window._emapp_yt_api_injected) {
            var tag = document.createElement('script');
            tag.src = "https://www.youtube.com/iframe_api";
            document.head.appendChild(tag);
            window._emapp_yt_api_injected = true;
        }

        // prepare player creation function
        window._emapp_create_players = function(){
            try {
                var iframesLocal = Array.from(document.querySelectorAll('iframe')).filter(f => f.src && f.src.match(/youtube\.com/));
                if(iframesLocal.length === 0) {
                    window._emapp_players_created_at = Date.now();
                    return {created:0};
                }
                if(typeof YT === 'undefined' || !YT.Player) {
                    // not ready yet
                    return {created:0, msg:'YT not ready'};
                }
                var createdCount = 0;
                iframesLocal.forEach(function(f){
                    try {
                        var vidId = null;
                        try {
                            // attempt to extract the video id from src
                            var p = new URL(f.src, location.href);
                            // embed path like /embed/VIDEOID or v=VIDEOID
                            var parts = p.pathname.split('/');
                            for(var j=0;j<parts.length;j++){
                                if(parts[j] && parts[j].length===11) { vidId = parts[j]; break; }
                            }
                            if(!vidId && p.searchParams.get('v')) vidId = p.searchParams.get('v');
                        } catch(e){}

                        var domId = f.id;
                        if(!domId) {
                            domId = 'emapp_iframe_' + Math.floor(Math.random()*100000);
                            f.id = domId;
                        }
                        // avoid recreating player for same iframe
                        if(window._emapp_players[domId] && window._emapp_players[domId].player) {
                            return;
                        }
                        // create player
                        var player = new YT.Player(domId, {
                            events: {
                                'onReady': function(event){
                                    try {
                                        var vid = null;
                                        try { vid = event.target.getVideoData().video_id; } catch(e){}
                                        window._emapp_players[domId] = window._emapp_players[domId] || {};
                                        window._emapp_players[domId].player = event.target;
                                        window._emapp_players[domId].videoId = vid;
                                        window._emapp_players[domId].state = event.target.getPlayerState ? event.target.getPlayerState() : null;
                                        window._emapp_players[domId].duration = (event.target.getDuration && typeof event.target.getDuration === 'function') ? event.target.getDuration() : null;
                                    } catch(e){}
                                },
                                'onStateChange': function(e){
                                    try {
                                        var dom = e.target.getIframe ? e.target.getIframe().id : null;
                                        var vid = null;
                                        try { vid = e.target.getVideoData().video_id; } catch(e){}
                                        var state = e.data;
                                        var recKey = dom || vid || ('p_' + Math.floor(Math.random()*100000));
                                        window._emapp_players[recKey] = window._emapp_players[recKey] || {};
                                        window._emapp_players[recKey].state = state;
                                        window._emapp_players[recKey].videoId = vid;
                                        if(e.target.getDuration) {
                                            try { window._emapp_players[recKey].duration = e.target.getDuration(); } catch(e) {}
                                        }
                                        if(state === YT.PlayerState.ENDED) {
                                            window._emapp_players[recKey].ended = true;
                                        }
                                    } catch(e){}
                                }
                            }
                        });
                        createdCount++;
                    } catch(e){}
                });
                window._emapp_player_ready = true;
                return {created: createdCount};
            } catch(err){
                return {err: String(err)};
            }
        };

        // ensure callback required by YouTube IFrame API
        window.onYouTubeIframeAPIReady = function(){
            try {
                window._emapp_yt_api_ready = true;
                // small delay and then create players
                setTimeout(function(){ window._emapp_create_players(); }, 500);
            } catch(e){}
        };

        // if YT already present and Player exists, create players now
        if(typeof YT !== 'undefined' && YT && YT.Player) {
            try { window._emapp_create_players(); window._emapp_yt_api_ready = true; } catch(e){}
        }

        // start HTML5 <video> tags (play)
        try {
            Array.from(document.querySelectorAll('video')).forEach(function(v){
                try { v.play().catch(function(){/*ignore*/}); } catch(e){}
            });
        } catch(e){}

        // attempt to start players once created; call playVideo for each
        setTimeout(function(){
            try {
                Object.keys(window._emapp_players || {}).forEach(function(k){
                    try {
                        var rec = window._emapp_players[k];
                        if(rec && rec.player && rec.player.playVideo) {
                            try { rec.player.playVideo(); } catch(e){}
                        }
                    } catch(e){}
                });
                // also trigger any newly created players
                try {
                    var created = window._emapp_create_players();
                    if(created && created.created) {
                        Object.keys(window._emapp_players||{}).forEach(function(k){
                            try { if(window._emapp_players[k].player && window._emapp_players[k].player.playVideo) window._emapp_players[k].player.playVideo(); } catch(e){}
                        });
                    }
                } catch(e){}
            } catch(e){}
        }, 1200);

        return {status: 'ok', iframes: iframes.length, html_videos: vids.length};

    } catch(ex) {
        return {status: 'error', err: String(ex)};
    }
})(arguments[0]);
"""

# JS helper to return current status snapshot (serializable)
GET_STATUS_JS = r"""
(function(){
    try {
        var out = {players: {}, html_videos: {}, timestamp: Date.now()};
        try {
            var pmap = window._emapp_players || {};
            Object.keys(pmap).forEach(function(k){
                try {
                    var r = pmap[k] || {};
                    out.players[k] = {
                        videoId: r.videoId || null,
                        state: (typeof r.state !== 'undefined') ? r.state : null,
                        ended: !!r.ended,
                        duration: r.duration || null
                    };
                } catch(e){}
            });
        } catch(e){}
        try {
            var hmap = window._emapp_html_videos || {};
            Object.keys(hmap).forEach(function(k){
                try {
                    var r = hmap[k] || {};
                    out.html_videos[k] = {ended: !!r.ended, started: !!r.started, duration: r.duration || null};
                } catch(e){}
            });
        } catch(e){}
        return out;
    } catch(e){
        return {err: String(e)};
    }
})();
"""

def wait_for_iframes_or_videos(driver, timeout):
    log("Waiting for iframes or <video> tags to appear (no hurry).")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            res = driver.execute_script("return (document.querySelectorAll('iframe[src*=\"youtube.com\"]').length || document.querySelectorAll('video').length) ;")
            if res and int(res) > 0:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False

def main():
    driver = None
    try:
        driver = setup_driver()
        log(f"Opening page: {PAGE_URL}")
        driver.get(PAGE_URL)

        # Wait patiently for iframes or HTML5 videos to appear
        appeared = wait_for_iframes_or_videos(driver, WAIT_IFRAMES_TIMEOUT)
        if not appeared:
            log("No iframes or HTML5 videos detected within wait timeout. Exiting.")
            driver.quit()
            return 1

        origin = up.urlparse(driver.current_url).scheme + "://" + up.urlparse(driver.current_url).netloc
        log(f"Origin resolved: {origin}")

        # Inject the setup JS which patches iframes, injects YT API and tries to start playback
        log("Injecting JS to create players and start playback (in-page).")
        setup_result = driver.execute_script(INJECT_JS_SETUP_PLAYERS, origin)
        log(f"Injection result: {setup_result}")

        # After injection, we should repeatedly call the create_players helper if API wasn't ready yet.
        # Give a long, patient loop: keep trying to create players and call playVideo until players exist.
        start_try = time.time()
        while True:
            # Trigger creation attempt
            try:
                driver.execute_script("if(window._emapp_create_players) { try { window._emapp_create_players(); } catch(e){} }")
            except Exception:
                pass

            # check status snapshot
            try:
                status = driver.execute_script(GET_STATUS_JS)
            except Exception as e:
                status = {"err": str(e)}

            # count players and html videos
            players = status.get("players", {}) if isinstance(status, dict) else {}
            html_videos = status.get("html_videos", {}) if isinstance(status, dict) else {}

            num_players = len(players)
            num_html = len(html_videos)
            log(f"Detected players: {num_players}, html_videos: {num_html}")

            # if at least one player or html video exists, break to playback-tracking stage
            if num_players + num_html > 0:
                break

            # otherwise wait and retry (this handles slow API load)
            if time.time() - start_try > WAIT_IFRAMES_TIMEOUT:
                log("Timeout waiting for players/html videos to be created. Exiting.")
                driver.quit()
                return 2
            time.sleep(2.0)

        # Kick all players and html videos to play again (best-effort)
        log("Attempting to start all players/videos (best-effort).")
        try:
            driver.execute_script("""
                try {
                    Object.keys(window._emapp_players||{}).forEach(function(k){
                        try { var p = window._emapp_players[k].player; if(p && p.playVideo) p.playVideo(); } catch(e){}
                    });
                } catch(e){}
                try { Array.from(document.querySelectorAll('video')).forEach(v=>{ try { v.play().catch(()=>{}); } catch(e){} }); } catch(e){}
            """)
        except Exception:
            pass

        log("Now monitoring until every player and HTML5 video reports ended. This may take a while.")
        # Poll until all ended
        while True:
            try:
                status = driver.execute_script(GET_STATUS_JS)
            except Exception as e:
                log(f"Error reading status: {e}")
                status = {"players":{}, "html_videos":{}}

            players = status.get("players", {}) if isinstance(status, dict) else {}
            html_videos = status.get("html_videos", {}) if isinstance(status, dict) else {}

            # check players: consider ended if ended==true OR state==0 (YT.PlayerState.ENDED)
            players_states = []
            for k, v in players.items():
                ended = v.get("ended", False)
                state = v.get("state", None)
                # YT ended state is 0
                if ended or state == 0:
                    players_states.append(True)
                else:
                    players_states.append(False)

            html_states = []
            for k, v in html_videos.items():
                html_states.append(bool(v.get("ended", False)))

            total = len(players_states) + len(html_states)
            ended_count = sum(1 for x in players_states if x) + sum(1 for x in html_states if x)

            log(f"Status snapshot: total={total}, ended={ended_count}. (players={len(players_states)}, html={len(html_states)})")

            if total == 0:
                # nothing to wait for — bail out
                log("No players or HTML5 videos to wait for. Exiting.")
                break

            if ended_count >= total:
                log("All players and HTML5 videos reported ended.")
                break

            time.sleep(POLL_INTERVAL)

        log("Cleanup: closing browser.")
        driver.quit()
        return 0

    except Exception as e:
        log(f"Fatal error: {e}")
        if driver:
            try:
                driver.quit()
            except:
                pass
        return 3

if __name__ == '__main__':
    exit(main())
