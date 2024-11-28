import time
import random
import asyncio
from http.cookiejar import MozillaCookieJar
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from cloudscraper import CloudScraper, create_scraper
from httpx import AsyncClient
from requests.cookies import cookiejar_from_dict

from ._types import BaseConfig, DownloadConfig
from .constant import BASE_URL, DOWNLOAD_LOG, HEADERS, SLEEP_TIME
from .utils import (
    AlbumTracker,
    LoginRequiredError,
    access_fail,
    download_photos,
    get_system_config_dir,
    parse_album_title,
    parse_album_urls,
    parse_input_url,
    parse_next_page_url,
    parse_page_num,
    parse_photo_urls,
    parse_url_mode,
)

if TYPE_CHECKING:
    from cloudscraper import CloudScraper

    from ._types import dl_status


logger = getLogger()


class Scrapper:
    """Asynchronous downloader for V2PH.com

    A scraper that handles downloading albums and photos from V2PH.com
    with support for multiple cookie files, concurrent downloads, and
    tracking of previously downloaded albums.

    Attributes:
        inputs (list[str]): List of input URLs or text files to download from
        download_dir (Path): Directory to save downloaded albums
        force_download (bool): Flag to force re-downloading of existing albums
        headers (dict[str, str]): HTTP headers for requests
        max_worker (int): Maximum number of concurrent download workers
        album_tracker (AlbumTracker): Tracks downloaded albums to prevent duplicates
    """

    def __init__(
        self,
        inputs: list[str] | str,
        cookie_files: list[str] | str,
        download_dir: str,
        force_download: bool,
        headers: dict[str, str],
        max_worker: int = 5,
    ) -> None:
        """Initialize Scrapper

        Args:
            inputs (list[str]): Download target from user input. Can be a list of txt file or urls.
            cookie_files (list[str]): Cookie files extracted from `find_cookie_files`.
            force_download (bool): Whether to skip downloaded url.
            headers: The header used for cloudscraper and httpx.
            max_worker: The maximum concurrency of the async download function.
        """
        self.inputs = inputs
        self.download_dir = Path(download_dir)
        self.force_download = force_download
        self.headers = headers
        self.max_worker = max_worker

        log_dir = get_system_config_dir() / DOWNLOAD_LOG
        self.album_tracker = AlbumTracker(log_dir)

        if not isinstance(self.inputs, list):
            self.inputs = [self.inputs]
        if not isinstance(cookie_files, list):
            self.cookie_files = [cookie_files]
        else:
            self.cookie_files = cookie_files

    async def run(self) -> None:
        """extract user input, looping around all the txt/urls and calls scrape method

        Iterates through inputs, skips already downloaded albums unless force_download is True,
        and triggers album scraping for each valid URL.
        """
        for input_ in self.inputs:
            urls = parse_input_url(input_)
            if not urls:
                logger.error(f"Warning: No valid URLs in {input_}")
                continue

            for url in urls:
                if self.album_tracker.is_downloaded(url) and not self.force_download:
                    logger.info(f"Album {url} already downloaded, skipping.")
                    continue
                await self.scrape(url)

    async def scrape(self, url: str) -> list["dl_status"]:
        """Input check and error management for a single url with multiple cookie files.

        Args:
            url (str): The processing url
        Return:
            dl_status: The download status, including a successful flag, url and destination
        """
        cookie_fail = False
        mode = parse_url_mode(url)

        for cookie_file in self.cookie_files:
            self.cf_sess, self.httpx_sess = Scrapper.create_session(cookie_file, self.headers)

            if cookie_fail:
                logger.info(f"Login fail. Switching to another cookie file {cookie_file}")
            else:
                logger.debug(f"Downloading with cookie file {Path(cookie_file).name}")

            try:
                self.warmup()
                self.transfer_parameters()
                return await self.scrape_selector(url=url, mode=mode)
            except LoginRequiredError as e:
                logger.error(e)
                cookie_fail = True
            except Exception as e:
                raise RuntimeError(f"RuntimeError: {e}") from e
        return []

    async def scrape_selector(self, url: str, mode: str) -> list["dl_status"]:
        """Select the scrape mode"""
        results = []

        if mode == "album":
            response = self.cf_sess.get(url)
            access_fail(response)
            start_page = parse_page_num(url)
            logger.info(f"Start scraping urls from {url}")

            album_alt = parse_album_title(response.text)
            album_dir = self.download_dir / album_alt

            base_config = BaseConfig(
                album_url=url,
                album_dir=album_dir,
                start_page=start_page,
                download=True,
            )
            results = await self.scrape_photo_urls(base_config)
        else:
            album_urls_with_alts = self.scrape_album_urls(self.cf_sess, url)
            start_page = 1
            for album_url, album_alt in album_urls_with_alts:
                album_dir = self.download_dir / album_alt

                base_config = BaseConfig(
                    album_url=album_url,
                    album_dir=album_dir,
                    start_page=start_page,
                    download=True,
                )
                results.extend(await self.scrape_photo_urls(base_config))

        return results

    def scrape_album_urls(self, cf_sess: "CloudScraper", start_url: str) -> list[tuple[str, str]]:
        """The mode that scrape the url of albums"""

        current_url: str | None = start_url
        album_urls_with_alts = []

        while current_url:
            response = cf_sess.get(current_url)
            access_fail(response)

            logger.info(f"Start scraping urls from {start_url}")
            album_urls_with_alts.extend(parse_album_urls(response.text))
            current_url = parse_next_page_url(response.text)
            time.sleep(SLEEP_TIME)

        return album_urls_with_alts

    async def scrape_photo_urls(self, config: BaseConfig) -> list["dl_status"]:
        """The mode that scrape the url of photos"""

        idx = 10 * (config.start_page - 1) + 1  # 10 images per page
        current_url: str | None = config.album_url
        semaphore = asyncio.Semaphore(self.max_worker)
        results = []

        while current_url:
            response = self.cf_sess.get(current_url)
            access_fail(response)
            self.transfer_parameters()

            urls = parse_photo_urls(response.text)

            if config.download:
                download_config = DownloadConfig(
                    download_dir=config.album_dir,
                    semaphore=semaphore,
                    session=self.httpx_sess,
                    start_idx=idx,
                    force_download=self.force_download,
                )
                results.extend(await download_photos(download_config, urls))
                idx += len(urls)

            current_url = parse_next_page_url(response.text)
            time.sleep(SLEEP_TIME)

        self.album_tracker.log_downloaded(config.album_url)
        return results

    def warmup(self) -> None:
        warmup_times = random.randint(1, 1)
        warmup_url = [
            "https://www.v2ph.com/actor/Umi-Shinonome",
            "https://www.v2ph.com/country/japan",
            "https://www.v2ph.com/category/magazine",
            "https://www.v2ph.com/category/short-hair",
        ]

        logger.info("warming up session")
        for _ in range(warmup_times):
            r = self.cf_sess.get(random.choice(warmup_url) + f"?page={random.randint(1, 20)}")
            access_fail(r, "process: warmup")
            time.sleep(random.uniform(0.1, 3.0))

    def transfer_parameters(self) -> None:
        self.httpx_sess.headers.update(dict(self.cf_sess.headers))  # type: ignore
        self.httpx_sess.cookies.clear()
        for k, v in dict(self.cf_sess.cookies).items():
            self.httpx_sess.cookies.set(k, v, BASE_URL)

    @staticmethod
    def create_session(
        cookie_file: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[CloudScraper, AsyncClient]:
        cf_sess = create_scraper()
        cookie_jar = MozillaCookieJar(cookie_file)
        cookie_jar.load()
        cookies_dict = {
            cookie.name: cookie.value for cookie in cookie_jar if cookie.value is not None
        }
        cf_sess.cookies = cookiejar_from_dict(cookies_dict)

        headers = headers or HEADERS
        cf_sess.headers.update(headers)

        httpx_sess = AsyncClient(headers=headers, cookies=cookie_jar, http2=True, timeout=15)

        return cf_sess, httpx_sess
