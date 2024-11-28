from asyncio import Semaphore
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from httpx import AsyncClient

from .constant import SPEED_LIMIT_KBPS

dl_status: TypeAlias = tuple[bool, str, str]


@dataclass
class DownloadConfig:
    download_dir: Path
    semaphore: Semaphore
    session: AsyncClient
    speed_limit_kbps: int = SPEED_LIMIT_KBPS
    start_idx: int = 1
    force_download: bool = False


@dataclass
class BaseConfig:
    album_url: str
    album_dir: Path
    start_page: int = 1
    download: bool = True
