import os
import time
import asyncio
import logging
import platform
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit

from httpx import AsyncClient, HTTPError
from lxml import html

from .constant import BASE_URL, VALID_PAGE

if TYPE_CHECKING:
    from requests import Response

    from ._types import DownloadConfig, dl_status

logger = logging.getLogger()


class AlbumTracker:
    """Download log in units of albums."""

    def __init__(self, download_log: str | Path) -> None:
        self.album_log_path = Path(download_log)

    def is_downloaded(self, album_url: str) -> bool:
        if os.path.exists(self.album_log_path):
            with open(self.album_log_path) as f:
                downloaded_albums = f.read().splitlines()
            return album_url in downloaded_albums
        return False

    def log_downloaded(self, album_url: str) -> None:
        if not self.is_downloaded(album_url):
            with open(self.album_log_path, "a") as f:
                f.write(album_url + "\n")


def parse_album_urls(html_content: str) -> list[tuple[str, str]]:
    tree = html.fromstring(html_content)
    album_links = tree.xpath(
        '//div[contains(@class, "row gutter-10 albums-list")]//a[contains(@class, "media-cover")]'
    )
    result = []
    for link in album_links:
        album_url = urljoin(BASE_URL, link.get("href"))
        img_tag = link.xpath('.//img[contains(@class, "card-img-top")]')
        album_alt = img_tag[0].get("alt", "").strip() if img_tag else "Untitled"
        result.append((album_url, album_alt))
    return result


def parse_photo_urls(html_content: str) -> list[Any]:
    path = '//div[@class="photos-list text-center"]//div[@class="album-photo my-2"]//img/@data-src'
    tree = html.fromstring(html_content)
    return tree.xpath(path)


def parse_album_title(html_content: str) -> str:
    path = '//div[contains(@class, "card-body")]//h1[contains(@class, "h5 text-center mb-3")]'
    tree = html.fromstring(html_content)
    title_element = tree.xpath(path)
    return title_element[0].text_content().strip() if title_element else ""


def parse_next_page_url(html_content: str) -> None | str:
    path_current_page = '//ul[contains(@class, "pagination")]//li[contains(@class, "active")]'
    path_next_page_item = 'following-sibling::li[contains(@class, "page-item")][1]/a'
    tree = html.fromstring(html_content)
    current_page = tree.xpath(path_current_page)
    if current_page:
        next_page_item = current_page[0].xpath(path_next_page_item)
        if next_page_item:
            return urljoin(BASE_URL, next_page_item[0].get("href"))
    return None


def parse_url_mode(url: str, valid_pages: list[str] = VALID_PAGE) -> str:
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


def parse_input_url(input_path: str) -> list[str]:
    """parse argparse download inputs, accept multiple urls input or multiple txt input"""

    # Check if input is a valid url, wrap it into a list
    if is_valid_url(input_path):
        return [input_path]

    # If input not a url, check if the file path exists.
    # Validate each url if the file exists, otherwise, return an empty list.
    try:
        with open(input_path) as f:
            return [line.strip() for line in f if is_valid_url(line.strip())]
    except Exception:
        return []


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


async def download(
    semaphore: asyncio.Semaphore,
    client: AsyncClient,
    url: str,
    dest: Path,
    headers: dict[str, str] | None,
    speed_limit_kbps: int,
) -> "dl_status":
    """Download with speed limit using an existing session.

    Args:
        semaphore (asyncio.Semaphore): The semaphore to restrict the concurrency
        client (httpx.AsyncClient): The request client session
        url (str): The download url
        dest (Path): The download destination
        headers (dict[str, str]): The header for requests client
        speed_limit_kbps (int): The download speed limit
    Returns:
        dl_status (tuple[bool, str, str]): The download status, a tuple with first term indicates
        download status, the second term is the download url and the last term is the destination.
    """
    if headers is None:
        headers = {}
    if speed_limit_kbps <= 0:
        raise ValueError("Speed limit must be a positive number.")

    chunk_size = 1024
    speed_limit_bps = speed_limit_kbps * 1024

    async with semaphore:
        async with client.stream("GET", url, headers=headers, timeout=30.0) as response:
            response.raise_for_status()
            with open(dest, "wb") as file:
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

    if os.path.exists(dest):
        actual_size = os.path.getsize(dest)
        lower_bound = downloaded * 0.99
        upper_bound = downloaded * 1.01
        if lower_bound <= actual_size <= upper_bound:
            return (True, url, str(dest))
    return (False, url, str(dest))


async def download_photos(
    config: "DownloadConfig",
    photo_urls: list[str],
) -> list["dl_status"]:
    """An async job submitter for download function"""

    download_tasks = []
    idx = config.start_idx

    for photo_url in photo_urls:
        file_name = f"{idx:03d}.{photo_url.split('.')[-1]}"
        dest = config.download_dir / file_name

        if not config.force_download:
            if dest.is_file():
                continue

        mkdir(config.download_dir)

        task = download(
            semaphore=config.semaphore,
            client=config.session,
            url=photo_url,
            dest=dest,
            headers=dict(config.session.headers),
            speed_limit_kbps=config.speed_limit_kbps,
        )
        download_tasks.append(task)
        idx += 1

    results = await asyncio.gather(*download_tasks)
    for r in results:
        if r[0]:
            logger.debug(f"Download success: {r[1]}")
        else:
            logger.error(f"Download fail, url: {r[1]}, dest: {r[2]}")
    return results


def get_system_config_dir() -> Path:
    """Return the config directory."""
    if platform.system() == "Windows":
        base = os.getenv("APPDATA", "")
    else:
        base = os.path.expanduser("~/.config")
    return Path(base) / "v2dl"


def find_cookie_files(config_dir: str | Path) -> list[str]:
    """Find all cookie files with 'cookie' in their names."""
    config_dir = Path(config_dir)
    return [
        str(file)
        for file in config_dir.iterdir()
        if file.is_file() and "cookie" in file.name and file.suffix == ".txt"
    ]


def suppress_log(log_level: int) -> None:
    level = logging.DEBUG if log_level == logging.DEBUG else logging.WARNING
    logging.getLogger("httpx").setLevel(level)
    logging.getLogger("httpcore").setLevel(level)


@lru_cache
def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def access_fail(response: "Response", msg: str | None = None) -> None:
    try:
        response.raise_for_status()
    except HTTPError as e:
        # Only catch response error, other exceptions will be passed to upper function
        raise HTTPError(f"HTTP request failed: {e} {msg or ''}")

    if login_fail(response):
        raise LoginRequiredError("LoginRequiredError: Login failed, please update your cookies")


def login_fail(response: "Response") -> bool:
    return response.url == urljoin(BASE_URL, "login")


class LoginRequiredError(Exception):
    """Check login error"""
