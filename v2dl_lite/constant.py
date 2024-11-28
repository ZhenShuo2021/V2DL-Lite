BASE_URL = "https://www.v2ph.com"
BASE_DIR = "v2dl"
SLEEP_TIME = 1.5
SPEED_LIMIT_KBPS = 200
MAX_WORKER = 3

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
HEADERS = {
    "Referer": BASE_URL,
    "User-Agent": UA,
    "Accept-Language": "zh-TW",
    "connection": "keep-alive",
}
VALID_PAGE = ["album", "actor", "company", "category", "country"]
DOWNLOAD_LOG = "downloaded_albums.txt"
