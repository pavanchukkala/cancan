# watch_videos.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Configure Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless=new")  # Headless mode for GitHub Actions
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Initialize driver
driver = webdriver.Chrome(options=chrome_options)

# Open the URL
url = 'http://emapp.cc/watch/[{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0},{"v":"VaWr_jHqcuE","t":0}]'
driver.get(url)
time.sleep(5)  # Wait for page to load

# Find all video elements
videos = driver.find_elements(By.TAG_NAME, "video")
print(f"Found {len(videos)} videos.")

# Play all videos sequentially
for index, video in enumerate(videos):
    driver.execute_script("arguments[0].play();", video)
    duration = driver.execute_script("return arguments[0].duration;", video)
    print(f"Playing video {index+1} ({duration} seconds)")
    time.sleep(duration + 1)  # Wait until video ends

print("All videos played. Closing browser.")
driver.quit()
