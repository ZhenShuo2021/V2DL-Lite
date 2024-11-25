import sys
import time
import asyncio
from pathlib import Path

from ._types import BaseConfig, CloudScraper, DownloadConfig
from .constant import HEADERS, SLEEP_TIME
from .options import parse_argument
from .utils import (
    access_fail,
    create_session,
    download,
    extract_album_urls,
    extract_photo_urls,
    find_cookie_files,
    get_album_title,
    get_next_page_url,
    get_url,
    mkdir,
    parse_page_num,
    parse_url_mode,
)


async def download_photos(
    config: DownloadConfig,
    photo_urls: list[str],
) -> list[bool]:
    download_tasks = []
    idx = config.start_idx

    for photo_url in photo_urls:
        file_name = f"{idx:03d}.{photo_url.split('.')[-1]}"
        download_dir_path = config.download_dir / file_name

        if config.skip:
            if download_dir_path.is_file():
                continue

        mkdir(config.download_dir)

        task = download(
            semaphore=config.semaphore,
            client=config.httpx_sess,
            url=photo_url,
            download_dir_path=download_dir_path,
            headers=dict(config.httpx_sess.headers),
            speed_limit_kbps=config.speed_limit_kbps,
        )
        download_tasks.append(task)
        idx += 1

    return await asyncio.gather(*download_tasks)


def scrape_album_urls(cf_sess: CloudScraper, start_url: str) -> list[tuple[str, str]]:
    current_url: str | None = start_url
    album_urls_with_alts = []

    while current_url:
        response = cf_sess.get(current_url)

        try:
            access_fail(response)
        except Exception as e:
            raise e

        album_urls_with_alts.extend(extract_album_urls(response.text))
        current_url = get_next_page_url(response.text)
        time.sleep(SLEEP_TIME)

    return album_urls_with_alts


async def scrape_photo_urls(config: BaseConfig) -> list[str]:
    idx = 10 * (config.start_page - 1)  # 10 images per page
    current_url: str | None = config.album_url
    semaphore = asyncio.Semaphore(config.max_worker)
    photo_urls = []

    while current_url:
        response = config.cf_sess.get(current_url)
        urls = extract_photo_urls(response.text)
        photo_urls.extend(urls)

        if config.download:
            download_config = DownloadConfig(
                httpx_sess=config.httpx_sess,
                download_dir=config.download_dir,
                semaphore=semaphore,
                start_idx=idx,
                skip=config.skip,
            )
            await download_photos(download_config, urls)
            idx += len(urls)

        current_url = get_next_page_url(response.text)
        time.sleep(SLEEP_TIME)

    return photo_urls


async def scrape_selector(
    url: str,
    download_dir: str,
    cookie_file: str,
    mode: str,
    skip: bool,
    max_worker: int = 5,
    headers: dict[str, str] = HEADERS,
) -> None:
    download_dir_ = Path(download_dir)
    cf_sess, httpx_sess = create_session(cookie_file, headers)

    if mode == "album":
        response = cf_sess.get(url)
        access_fail(response)
        start_page = parse_page_num(url)

        album_alt = get_album_title(response.text)
        album_dir = download_dir_ / album_alt

        base_config = BaseConfig(
            cf_sess=cf_sess,
            httpx_sess=httpx_sess,
            album_url=url,
            download_dir=album_dir,
            start_page=start_page,
            max_worker=max_worker,
            download=True,
            skip=skip,
        )
        await scrape_photo_urls(base_config)
    else:
        album_urls_with_alts = scrape_album_urls(cf_sess, url)
        start_page = 1
        for album_url, album_alt in album_urls_with_alts:
            album_dir = download_dir_ / album_alt

            base_config = BaseConfig(
                cf_sess=cf_sess,
                httpx_sess=httpx_sess,
                album_url=album_url,
                download_dir=album_dir,
                start_page=start_page,
                max_worker=max_worker,
                download=True,
                skip=skip,
            )
            await scrape_photo_urls(base_config)


async def scrape(
    input_path: str,
    download_dir: str,
    skip: bool,
    cookie_files: list[Path],
    max_worker: int = 1,
    headers: dict[str, str] = HEADERS,
) -> None:
    cookie_fail = False
    valid_pages: list[str] = ["album", "actor", "company", "category", "country"]

    urls = get_url(input_path)

    for url in urls:
        mode = parse_url_mode(url, valid_pages)

        for cookie_file in cookie_files:
            if cookie_fail:
                print(f"Login fail for previous cookie file. Use new cookie file {cookie_file} ...")
            else:
                print(f"Downloading {url} with cookie file {cookie_file} ...")

            try:
                await scrape_selector(
                    url=url,
                    download_dir=download_dir,
                    cookie_file=str(cookie_file),
                    mode=mode,
                    skip=skip,
                    max_worker=max_worker,
                    headers=headers,
                )
                cookie_fail = False
                break
            except Exception as e:
                print(f"Scrape error for {url}: {e}")
                cookie_fail = True
                continue


def main() -> int:
    args = parse_argument()
    cookie_files = find_cookie_files(args.cookies_path)
    max_worker = 3

    if not cookie_files:
        return 1

    headers = HEADERS
    if args.language:
        headers["Accept-Language"] = args.language

    for input_path in args.inputs:
        urls = get_url(input_path)
        if not urls:
            print(f"Warning: No valid URLs in {input_path}", file=sys.stderr)
            continue

        for url in urls:
            try:
                asyncio.run(
                    scrape(
                        url,
                        args.download_dir,
                        args.skip,
                        cookie_files,
                        max_worker=max_worker,
                        headers=headers,
                    ),
                )
            except Exception as e:
                print(f"Error with {url}: {e}", file=sys.stderr)

    return 0
