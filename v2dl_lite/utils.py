import os
import time
import asyncio
import platform
from functools import lru_cache
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from cloudscraper import CloudScraper, create_scraper
from httpx import AsyncClient, HTTPError

from .constant import BASE_URL, HEADERS

if TYPE_CHECKING:
    from requests import Response


def create_session(
    cookie_file: str,
    headers: dict[str, str] | None = None,
) -> tuple[CloudScraper, AsyncClient]:
    cf_sess = create_scraper()
    cookie_jar = MozillaCookieJar(cookie_file)
    cookie_jar.load()
    cf_sess.cookies = cookie_jar

    headers = headers or HEADERS
    cf_sess.headers.update(headers)

    httpx_sess = AsyncClient(headers=headers, cookies=cookie_jar, http2=True, timeout=15)

    return cf_sess, httpx_sess


def extract_album_urls(html_content: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_content, "html.parser")
    albums_list = soup.find("div", class_="row gutter-10 albums-list")
    album_links = albums_list.find_all("a", class_="media-cover")

    result = []
    for link in album_links:
        album_url = urljoin(BASE_URL, link["href"])
        img_tag = link.find("img", class_="card-img-top")
        album_alt = img_tag["alt"].strip() if img_tag and img_tag.has_attr("alt") else "Untitled"
        result.append((album_url, album_alt))
    return result


def extract_photo_urls(html_content: str) -> list[Any]:
    soup = BeautifulSoup(html_content, "html.parser")
    photos_list = soup.find("div", class_="photos-list text-center")
    photo_divs = photos_list.find_all("div", class_="album-photo my-2")
    return [
        img["data-src"] for div in photo_divs if (img := div.find("img")) and img.get("data-src")
    ]


def get_next_page_url(html_content: str) -> None | str:
    soup = BeautifulSoup(html_content, "html.parser")
    pagination = soup.find("ul", class_="pagination")
    if not pagination:
        return None

    current_page = pagination.find("li", class_="active")
    if not current_page:
        return None

    next_page_item = current_page.find_next_sibling("li", class_="page-item")
    if next_page_item and next_page_item.find("a"):
        return urljoin(BASE_URL, next_page_item.find("a")["href"])
    return None


def get_album_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title_element = soup.select_one(".card-body h1.h5.text-center.mb-3")
    if title_element:
        return title_element.get_text(strip=True)
    return ""


def parse_url_mode(url: str, valid_pages: list[str]) -> str:
    if not url.startswith(BASE_URL):
        raise ValueError(f"URL must start with {BASE_URL}, got {url}")

    parsed_url = urlsplit(url)
    path_segments = parsed_url.path.strip("/").split("/")

    if not path_segments:
        raise ValueError(f"Invalid URL: {url}")

    mode = path_segments[0]
    if mode not in valid_pages:
        raise ValueError(f"Unsupported mode: {mode}")

    return mode


def parse_page_num(url: str) -> int:
    """parse page url, default is 1"""
    parsed_url = urlsplit(url)
    query_params = parse_qs(parsed_url.query)
    return int(query_params.get("page", ["1"])[0])


def get_url(input_path: str) -> list[str]:
    if input_path.startswith(("http://", "https://")):
        return [input_path]

    try:
        with open(input_path) as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []


async def download(
    semaphore: asyncio.Semaphore,
    client: AsyncClient,
    url: str,
    download_dir_path: Path,
    headers: dict[str, str] | None,
    speed_limit_kbps: int,
) -> bool:
    """Download with speed limit using an existing session."""
    if headers is None:
        headers = {}
    if speed_limit_kbps <= 0:
        raise ValueError("Speed limit must be a positive number.")

    chunk_size = 1024
    speed_limit_bps = speed_limit_kbps * 1024

    async with semaphore:
        async with client.stream("GET", url, headers=headers, timeout=30.0) as response:
            response.raise_for_status()
            with open(download_dir_path, "wb") as file:
                downloaded = 0
                start_time = time.time()

                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    if not chunk:
                        break
                    file.write(chunk)
                    downloaded += len(chunk)
                    elapsed_time = time.time() - start_time
                    expected_time = downloaded / speed_limit_bps
                    if elapsed_time < expected_time:
                        await asyncio.sleep(expected_time - elapsed_time)

    if os.path.exists(download_dir_path):
        actual_size = os.path.getsize(download_dir_path)
        lower_bound = downloaded * 0.99
        upper_bound = downloaded * 1.01
        if lower_bound <= actual_size <= upper_bound:
            return True
    return False


def get_system_config_dir() -> Path:
    """Return the config directory."""
    if platform.system() == "Windows":
        base = os.getenv("APPDATA", "")
    else:
        base = os.path.expanduser("~/.config")
    return Path(base) / "v2dl"


def find_cookie_files(config_dir: Path) -> list[Path]:
    """Find all cookie files with 'cookie' in their names."""
    return [
        file
        for file in config_dir.iterdir()
        if file.is_file() and "cookie" in file.name and file.suffix == ".txt"
    ]


def access_fail(response: "Response") -> None:
    try:
        response.raise_for_status()
    except HTTPError as e:
        raise AccessError(
            f"HTTP request failed: {e}",
            url=response.url,
            response_status=response.status_code,
        )

    if login_fail(response):
        raise LoginRequiredError("Login required", url=response.url)


def login_fail(response: "Response") -> bool:
    return response.url == urljoin(BASE_URL, "login")


@lru_cache
def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


class AccessError(Exception):
    def __init__(self, message: str, url: str, response_status: int | None = None):
        super().__init__(message)
        self.url = url
        self.response_status = response_status


class LoginRequiredError(AccessError):
    pass
