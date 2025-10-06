# watch_videos.py
# Selenium script that opens the provided URL, tries to play all videos,
# waits until each finishes, then closes the browser.
# Improved for GitHub Actions: autoplay flags, long polling, multiple play strategies.

import time, json, sys, traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = r'http://emapp.cc/watch/[{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0}]'

# Timeouts
POLL_TIMEOUT = 90         # seconds to wait for video elements to appear
POLL_INTERVAL = 1.0       # polling interval
PLAYBACK_SLACK = 1.5      # extra seconds after duration

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def setup_driver():
    chrome_options = Options()
    # Use the new headless mode on modern Chrome; if you want headed, remove headless
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--disable-gpu")
    # IMPORTANT: allow autoplay even without user gesture
    chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    # optional: set user agent if site blocks bots
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    # Make webdriver-manager install driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

def find_video_count(driver):
    try:
        return driver.execute_script("return document.querySelectorAll('video').length")
    except Exception:
        return 0

def get_videos(driver):
    try:
        return driver.find_elements(By.TAG_NAME, "video")
    except Exception:
        return []

def try_play_via_js(driver, elem):
    try:
        driver.execute_script("arguments[0].play();", elem)
        return True
    except Exception:
        return False

def try_click_play_buttons(driver):
    # Common patterns for custom play buttons - try clickable elements
    candidates = []
    try:
        candidates += driver.find_elements(By.CSS_SELECTOR, "button.play, .play-button, .vjs-play-control, .ytp-large-play-button, .play")
        candidates += driver.find_elements(By.CSS_SELECTOR, "[role='button']")
    except Exception:
        pass

    clicked = 0
    for el in candidates:
        try:
            if el.is_displayed():
                el.click()
                clicked += 1
        except Exception:
            pass
    return clicked

def attempt_space_on_elements(driver):
    # Focus the body and send space, sometimes toggles play on focused players
    try:
        ActionChains(driver).send_keys(Keys.SPACE).perform()
        return True
    except Exception:
        return False

def wait_and_play_all(driver):
    # Poll for video elements
    log("Waiting for video elements to appear (up to {}s)".format(POLL_TIMEOUT))
    start = time.time()
    videos = []
    while time.time() - start < POLL_TIMEOUT:
        videos = get_videos(driver)
        if videos and len(videos) > 0:
            break
        # also try clicking play buttons in case videos are within custom containers
        try_click_play_buttons(driver)
        attempt_space_on_elements(driver)
        time.sleep(POLL_INTERVAL)

    count = len(videos)
    log(f"Found {count} videos.")
    if count == 0:
        # Extra attempt: look for iframes (YouTube players) and try to click overlay play buttons
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log(f"Also found {len(iframes)} iframes — trying to click overlay play buttons in page context.")
        try_click_play_buttons(driver)
        # final re-check
        videos = get_videos(driver)
        count = len(videos)
        log(f"After fallback attempts: {count} videos found.")
    if count == 0:
        log("No <video> elements detected. This page may use cross-origin iframes or JS that prevents headless detection.")
        return 0

    # Try to play each <video> element and wait for it to finish
    for idx, v in enumerate(videos):
        try:
            log(f"Attempting to play video {idx+1}/{count}")
            played = try_play_via_js(driver, v)
            if not played:
                log("JS play() failed; trying to click its center.")
                try:
                    # click center of element
                    ActionChains(driver).move_to_element(v).click().perform()
                    played = True
                except Exception:
                    played = False
            # fallback: try clicking common play buttons again
            if not played:
                try_click_play_buttons(driver)
            # give it a moment to start
            time.sleep(0.8)
            # read duration
            duration = None
            try:
                duration = driver.execute_script("return arguments[0].duration || 0;", v)
            except Exception:
                duration = 0
            try:
                current = driver.execute_script("return arguments[0].currentTime || 0;", v)
            except Exception:
                current = 0
            if duration and duration > 0:
                to_wait = max(0, duration - current) + PLAYBACK_SLACK
                log(f"Video {idx+1} duration: {duration:.1f}s, current: {current:.1f}s -> waiting {to_wait:.1f}s")
                time.sleep(to_wait)
            else:
                # if no duration available, wait a conservative default
                fallback_wait = 8
                log(f"Video {idx+1} has no duration (likely streaming or iframe). Waiting {fallback_wait}s as fallback.")
                time.sleep(fallback_wait)
        except Exception as e:
            log(f"Error while playing video {idx+1}: {e}\n{traceback.format_exc()}")
    return count

def main():
    driver = None
    try:
        driver = setup_driver()
        log(f"Opening URL: {URL}")
        driver.get(URL)
        # give main scripts time to execute
        time.sleep(3)
        count = wait_and_play_all(driver)
        log("All videos attempted. Closing browser.")
        driver.quit()
        log("Done.")
        return 0 if count >= 0 else 1
    except Exception as e:
        log(f"Fatal error: {e}\n{traceback.format_exc()}")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        return 2

if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
