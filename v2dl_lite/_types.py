from asyncio import Semaphore
from dataclasses import dataclass
from pathlib import Path

from cloudscraper import CloudScraper
from httpx import AsyncClient

from .constant import SPEED_LIMIT_KBPS

__all__ = ["CloudScraper"]


@dataclass
class DownloadConfig:
    httpx_sess: AsyncClient
    download_dir: Path
    semaphore: Semaphore
    speed_limit_kbps: int = SPEED_LIMIT_KBPS
    start_idx: int = 1
    skip: bool = False


@dataclass
class BaseConfig:
    cf_sess: CloudScraper
    httpx_sess: AsyncClient
    album_url: str
    download_dir: Path
    start_page: int = 1
    max_worker: int = 5
    download: bool = True
    skip: bool = False
