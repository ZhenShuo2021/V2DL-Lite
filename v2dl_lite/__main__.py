import asyncio
from pathlib import Path

from v2dl_lite.constant import HEADERS, MAX_WORKER
from v2dl_lite.logger import setup_logging
from v2dl_lite.options import parse_argument
from v2dl_lite.scrapper import Scrapper
from v2dl_lite.utils import find_cookie_files, suppress_log


def main() -> int:
    headers = HEADERS
    max_worker = MAX_WORKER
    args = parse_argument()
    cookie_files = find_cookie_files(Path(args.cookies_path))
    logger = setup_logging(level=args.log_level)
    suppress_log(args.log_level)

    if not cookie_files:
        return 1

    if args.language:
        headers["Accept-Language"] = args.language

    # chr(10): "\n"
    logger.info(f"""
Your download configuration:
----------------------------------------------------------
Download base folder: {args.download_dir}
{chr(10).join(f"Cookies file: {file}" for file in cookie_files)}
Skipping downloaded albums? {"Yes" if args.force else "No"}
----------------------------------------------------------
""")

    scrapper = Scrapper(
        args.inputs,
        cookie_files,
        args.download_dir,
        args.force,
        headers,
        max_worker,
    )
    asyncio.run(scrapper.run())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
