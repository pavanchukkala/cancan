import time, json, sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# The URL you provided
URL = r'http://emapp.cc/watch/[{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0}]'

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def extract_video_ids(url):
    try:
        start = url.index('[')
        end = url.rindex(']') + 1
        data = url[start:end]
        arr = json.loads(data)
        ids = [item['v'] for item in arr]
        return ids
    except Exception as e:
        log(f"Failed to parse video IDs: {e}")
        return []

def setup_driver():
    options = Options()
    options.add_argument("--headless=new")   # remove if you want a visible browser
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--mute-audio")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver

def watch_video(driver, video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    log(f"Opening YouTube video: {url}")
    driver.get(url)
    try:
        # Wait for video element or play button
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )
        # Play video using JS (works for HTML5 YouTube player)
        driver.execute_script("document.querySelector('video').play();")
        # Get duration
        duration = driver.execute_script("return document.querySelector('video').duration")
        log(f"Video duration: {duration:.1f}s, waiting to finish")
        time.sleep(duration + 1.5)  # small buffer
    except Exception as e:
        log(f"Error playing video {video_id}: {e}")
        # fallback: wait fixed time
        time.sleep(10)

def main():
    ids = extract_video_ids(URL)
    if not ids:
        log("No video IDs found. Exiting.")
        sys.exit(1)

    driver = setup_driver()
    try:
        for vid in ids:
            watch_video(driver, vid)
        log("All videos watched. Closing browser.")
        driver.quit()
    except Exception as e:
        log(f"Fatal error: {e}")
        driver.quit()
        sys.exit(1)

if __name__ == "__main__":
    main()
