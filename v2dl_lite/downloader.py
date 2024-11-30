import os
import re
import sys
import time
import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from mimetypes import guess_extension
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from httpx import AsyncClient, HTTPError
from pathvalidate import sanitize_filename

# from requests.cookies import cookiejar_from_dict
from ._types import Dl_Status, PathType, Valid_Session
from .constant import BASE_URL, BROWSER, HEADERS, SPEED_LIMIT_KBPS
from .utils import add_underscore_before_first_number, auto_await

if TYPE_CHECKING:
    import httpx
    from curl_cffi.requests.models import Response as curl_Response


logger = logging.getLogger()


@dataclass
class DownloadConfig:
    download_dir: Path
    semaphore: asyncio.Semaphore
    session: "BaseSession"
    speed_limit_kbps: int = SPEED_LIMIT_KBPS
    start_idx: int = 1
    force_download: bool = False


class BaseResponse(ABC):
    @abstractmethod
    def json(self) -> Any:
        pass

    @property
    @abstractmethod
    def text(self) -> str:
        pass

    @property
    def headers(self) -> dict[Any, Any]:
        return self.response.headers

    @abstractmethod
    def raise_for_status(self) -> None:
        pass

    @property
    @abstractmethod
    def url(self) -> Any:
        pass

    @property
    @abstractmethod
    def response(self) -> Any:  # 定義抽象屬性，返回原始的 response 對象
        pass


class HttpxResponse(BaseResponse):
    def __init__(self, response: "httpx.Response") -> None:
        self._response = response

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def url(self) -> "httpx.URL":
        return self._response.url

    @property
    def response(self) -> "httpx.Response":
        return self._response

    def json(self) -> Any:
        return self._response.json()

    def raise_for_status(self) -> None:
        _ = self._response.raise_for_status()


class CurlResponse(BaseResponse):
    def __init__(self, response: "curl_Response") -> None:
        self._response = response

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def url(self) -> str:
        return self._response.url

    @property
    def response(self) -> "curl_Response":
        return self._response

    def json(self) -> Any:
        return self._response.json()

    def raise_for_status(self) -> None:
        self._response.raise_for_status()


class PrimpResponse(BaseResponse):
    def __init__(self, response: Any) -> None:
        self._response = response

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def url(self) -> str:
        return self._response.url

    @property
    def response(self) -> Any:
        return self._response

    def json(self) -> Any:
        return self._response.json()

    def raise_for_status(self) -> None:
        if self._response.status_code >= 400:
            raise HTTPError(f"HTTP Error (primp): {self._response.status_code}")


class BaseSession(ABC):
    def __init__(
        self,
        cookies_path: str,
        headers: dict[str, str],
        timeout: int = 15,
    ) -> None:
        self.cookies, self.headers = prepare_session(cookies_path, headers)
        self.timeout = timeout

    @abstractmethod
    async def get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse: ...

    @auto_await
    @abstractmethod
    async def sync_get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        raise NotImplementedError("auto_await not implemented yet")

    @abstractmethod
    async def post(
        self, url: str, data: dict[Any, Any], *args: Any, **kwargs: Any
    ) -> BaseResponse: ...

    @abstractmethod
    async def stream(
        self,
        semaphore: asyncio.Semaphore,
        url: str,
        dest: Path,
        speed_limit_kbps: int,
        *args: Any,
        **kwargs: Any,
    ) -> Dl_Status:
        """Download with speed limit using an existing session.

        Args:
            semaphore (asyncio.Semaphore): The semaphore to restrict the concurrency
            client (Client): The request client session, can be a httpx/curl-cffi/primp session
            url (str): The download url
            dest (Path): The download destination (Note: DO NOT include extension)
            headers (dict[str, str]): The header for requests client
            speed_limit_kbps (int): The download speed limit
        Returns:
            dl_status (tuple[bool, str, str]): The download status, a tuple with first term indicates
            download status, the second term is the download url and the last term is the destination.
        """


class HttpxSession(BaseSession):
    def __init__(
        self,
        cookies_path: str,
        headers: dict[str, str],
        timeout: int,
    ) -> None:
        super().__init__(cookies_path, headers, timeout)
        self.session = AsyncClient(headers=headers, cookies=self.cookies, http2=True, timeout=15)

    async def get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.get(url, *args, **kwargs)
        return HttpxResponse(response)

    @auto_await
    async def sync_get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.get(url, *args, **kwargs)
        return HttpxResponse(response)

    async def post(self, url: str, data: dict[Any, Any], *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.post(url, *args, json=data, **kwargs)
        return HttpxResponse(response)

    async def stream(
        self,
        semaphore: asyncio.Semaphore,
        url: str,
        dest: Path,
        speed_limit_kbps: int,
        *args: Any,
        **kwargs: Any,
    ) -> Dl_Status:
        chunk_size = kwargs.get("chunk_size", 0)
        if speed_limit_kbps <= 0:
            raise ValueError("Speed limit must be a positive number.")

        speed_limit_bps = speed_limit_kbps * 1024

        async with semaphore:
            async with self.session.stream("GET", url, timeout=30.0) as response:
                response.raise_for_status()
                ext = "." + DownloadPathTool.get_ext(response)  # type: ignore
                dest = dest.with_suffix(ext)

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

        return download_check(url, dest, downloaded)


class CurlSession(BaseSession):
    def __init__(
        self,
        cookies_path: str,
        headers: dict[str, str],
        timeout: int,
    ) -> None:
        super().__init__(cookies_path, headers, timeout)
        try:
            from curl_cffi.requests import AsyncSession

            self.session = AsyncSession(
                cookies=self.cookies, headers=self.headers, timeout=15, impersonate=BROWSER
            )

        except ModuleNotFoundError:
            raise ImportError("curl_requests module is required for CurlCffiAdapter.")

    async def get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.get(url, **kwargs)
        return CurlResponse(response)

    @auto_await
    async def sync_get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.get(url, *args, **kwargs)
        return CurlResponse(response)

    async def post(self, url: str, data: dict[Any, Any], *args: Any, **kwargs: Any) -> BaseResponse:
        response = await self.session.post(url, json=data, **kwargs)
        return CurlResponse(response)

    async def stream(
        self,
        semaphore: asyncio.Semaphore,
        url: str,
        dest: Path,
        speed_limit_kbps: int,
        *args: Any,
        **kwargs: Any,
    ) -> Dl_Status:
        async with semaphore:
            if speed_limit_kbps <= 0:
                raise ValueError("Speed limit must be a positive number.")

            speed_limit_bps = speed_limit_kbps * 1024

            response = await self.session.get(url, stream=True)
            response.raise_for_status()
            ext = "." + DownloadPathTool.get_ext(response)  # type: ignore
            dest = dest.with_suffix(ext)

            with open(dest, "wb") as f:
                downloaded = 0
                start_time = time.time()

                async for chunk in response.aiter_content():  # chunk size not possible for curl
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    elapsed_time = time.time() - start_time
                    expected_time = downloaded / speed_limit_bps
                    if elapsed_time < expected_time:
                        await asyncio.sleep(expected_time - elapsed_time)

        return download_check(url, dest, downloaded)


# TODO: Wait for AsyncClient feature https://github.com/deedy5/primp
class PrimpSession(BaseSession):
    def __init__(
        self,
        cookies_path: str,
        headers: dict[str, str],
        timeout: int,
    ) -> None:
        super().__init__(cookies_path, headers, timeout)
        try:
            import primp  # type: ignore

            browser = add_underscore_before_first_number(BROWSER)
            # headers will be ignored with impersonate is set
            self.session = primp.Client(cookies=self.cookies, impersonate=browser, http2=True)  # type: ignore
        except ModuleNotFoundError:
            raise ImportError(
                "primp module not found, please install primp with `pip install v2dl-lite[ja4]`."
            )

    async def get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        raise NotImplementedError(
            "primp method is under developing, see https://github.com/deedy5/primp"
        )

    @auto_await
    def sync_get(self, url: str, *args: Any, **kwargs: Any) -> BaseResponse:
        response = self.session.get(url, *args, **kwargs)
        return PrimpResponse(response)

    async def post(self, url: str, data: dict[Any, Any], *args: Any, **kwargs: Any) -> BaseResponse:
        raise NotImplementedError(
            "primp method is under developing, see https://github.com/deedy5/primp"
        )

    async def stream(
        self,
        semaphore: asyncio.Semaphore,
        url: str,
        dest: Path,
        speed_limit_kbps: int,
        chunk_size: int,
        *args: Any,
        **kwargs: Any,
    ) -> Dl_Status:
        raise NotImplementedError


class DownloadPathTool:
    """Handles file and directory operations."""

    @staticmethod
    def mkdir(folder_path: PathType) -> None:
        """Ensure the folder exists, create it if not."""
        Path(folder_path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_file_exists(file_path: PathType, no_skip: bool, logger: logging.Logger) -> bool:
        """Check if the file exists and log the status."""
        if Path(file_path).exists() and not no_skip:
            logger.info("File already exists: '%s'", file_path)
            return True
        return False

    @staticmethod
    def get_file_dest(
        download_root: PathType,
        album_name: str,
        filename: str,
        extension: str | None = None,
    ) -> Path:
        """Construct the file path for saving the downloaded file.

        Args:
            download_root (PathType): The base download folder for v2dl
            album_name (str): The name of the download album, used for the sub-directory
            filename (str): The name of the target download file
            extension (str | None): The file extension of the target download file
        Returns:
            PathType: The full path of the file
        """
        ext = f".{extension}" if extension else ""
        folder = Path(download_root) / sanitize_filename(album_name)
        sf = sanitize_filename(filename)
        return folder / f"{sf}{ext}"

    @staticmethod
    def get_image_ext(url: str, default_ext: str = "jpg") -> str:
        """Get the extension of a URL."""
        image_extensions = r"\.(jpg|jpeg|png|gif|bmp|webp|tiff|svg)(?:\?.*|#.*|$)"
        match = re.search(image_extensions, url, re.IGNORECASE)
        if match:
            # Normalize 'jpeg' to 'jpg'
            return "jpg" if match.group(1).lower() == "jpeg" else match.group(1).lower()
        return default_ext

    @staticmethod
    def get_ext(
        response: BaseResponse,
        default_method: Callable[[str, str], str] | None = None,
    ) -> str:
        """Guess file extension based on response Content-Type."""
        if default_method is None:
            default_method = DownloadPathTool.get_image_ext

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        extension = guess_extension(content_type)
        if extension:
            return extension.lstrip(".")

        return default_method(str(response.url), "jpg")

    @staticmethod
    def check_input_file(input_path: PathType) -> None:
        if input_path and not os.path.isfile(input_path):
            logging.error("Input file %s does not exist.", input_path)
            sys.exit(1)
        else:
            logging.info("Input file %s exists and is accessible.", input_path)


def create_session(
    client: Valid_Session,
    cookies_path: str,
    headers: dict[str, str] = HEADERS,
    timeout: int = 15,
    **kwargs: dict[Any, Any],
) -> BaseSession:
    client_map: dict[Valid_Session, Callable[..., Any]] = {
        "httpx": lambda: HttpxSession(cookies_path, headers, timeout, **kwargs),
        "curl": lambda: CurlSession(cookies_path, headers, timeout, **kwargs),
        "primp": lambda: PrimpSession(cookies_path, headers, timeout, **kwargs),
    }

    try:
        return client_map[client]()
    except KeyError:
        raise ValueError(f"Unknown session_type: {client}")


async def download_photos(
    config: "DownloadConfig",
    photo_urls: list[str],
) -> list[Dl_Status]:
    """An async job submitter for download function"""

    download_tasks = []
    idx = config.start_idx

    for photo_url in photo_urls:
        file_name = f"{idx:03d}"
        dest = config.download_dir / file_name

        if not config.force_download:
            if dest.is_file():
                continue

        DownloadPathTool.mkdir(config.download_dir)
        task = config.session.stream(
            semaphore=config.semaphore,
            client=config.session,
            url=photo_url,
            dest=dest,
            speed_limit_kbps=config.speed_limit_kbps,
            chunk_size=4096,
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


def download_check(url: str, dest: str | Path, downloaded: float) -> Dl_Status:
    if os.path.exists(dest):
        actual_size = os.path.getsize(dest)
        lower_bound = downloaded * 0.9999
        upper_bound = downloaded * 1.0001
        if lower_bound <= actual_size <= upper_bound:
            return (True, url, str(dest))
    return (False, url, str(dest))


def prepare_session(cookie_file: str, headers: dict[str, str]) -> tuple[Any, dict[str, str]]:
    if os.path.isfile(cookie_file):
        cookie_jar = MozillaCookieJar(cookie_file)
        cookie_jar.load()
        cookies_dict = {c.name: c.value for c in cookie_jar if c.value is not None}
    else:
        cookies_dict = {}
    # cookies = cookiejar_from_dict(cookies_dict)
    return cookies_dict, headers


def access_fail(response: BaseResponse, msg: str | None = None) -> None:
    try:
        response.raise_for_status()
    except HTTPError as e:
        # Only catch response error, other exceptions will be passed to upper function
        raise HTTPError(f"HTTP request failed: {e} {msg or ''}")

    if login_fail(response):
        raise LoginRequiredError("LoginRequiredError: Login failed, please update your cookies")


def login_fail(response: BaseResponse) -> bool:
    return response.url == urljoin(BASE_URL, "login")


class LoginRequiredError(Exception):
    """Check login error"""


class ConnectError(Exception):
    """Network status code error"""
