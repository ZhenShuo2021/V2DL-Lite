import os
import re
import logging
import platform
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit

from lxml import html

from .constant import BASE_URL, VALID_PAGE

if TYPE_CHECKING:
    pass

logger = logging.getLogger()
VALID_CLIENT = Literal["httpx", "curl", "primp"]


@dataclass
class BaseConfig:
    album_url: str
    album_dir: Path
    start_page: int = 1
    download: bool = True


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


def parse_url_mode(url: str, valid_pages: tuple[str, ...] = VALID_PAGE) -> str:
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


def add_underscore_before_first_number(input_string: str) -> str:
    return re.sub(r"(?=\d)", "_", input_string, count=1)


def auto_await(func: Callable[..., Any]) -> Callable[..., Any]:
    # TODO: blocking and run async function or run normal function
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = func(*args, **kwargs)
        raise NotImplementedError(str(result) + "auto await wrapper not yet implemented")

    return wrapper
