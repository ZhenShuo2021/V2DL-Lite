BASE_URL = "https://www.v2ph.com"
BASE_DIR = "v2dl"
SLEEP_TIME = 5
SPEED_LIMIT_KBPS = 400
MAX_WORKER = 5
DOWNLOAD_LOG = "downloaded_albums.txt"

BROWSER = "chrome124"  # for primp/curl-cffi
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36"
HEADERS = {
    "Referer": BASE_URL,
    "User-Agent": UA,
    "Accept-Language": "zh-TW",
}
VALID_PAGE = ("album", "actor", "company", "category", "country")
