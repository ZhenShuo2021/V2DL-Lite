import sys
import argparse
from pathlib import Path

from .constant import BASE_DIR
from .utils import get_system_config_dir
from .version import __version__


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, prog) -> None:  # type: ignore
        super().__init__(prog, max_help_position=36)


def parse_argument() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lite version of V2PH-Downloader",
        formatter_class=CustomHelpFormatter,
    )

    parser.add_argument(
        "inputs",
        nargs="*",
        help="URLs or text files containing URLs (one per line)",
    )

    parser.add_argument(
        "--skip",
        "-s",
        action="store_true",
        help="Skip already downloaded files",
    )

    parser.add_argument(
        "--download-dir",
        "-d",
        default=str(Path.home() / "Downloads" / BASE_DIR),
        help=f"Download directory (default: ~/Downloads/{BASE_DIR})",
    )

    parser.add_argument(
        "--cookies-path",
        "-c",
        default=get_system_config_dir(),
        help=f"Path to cookies directory (default: ~/.config/{BASE_DIR})",
    )

    parser.add_argument(
        "--language",
        "-l",
        default="zh-TW",
        help="Preferred language, used for naming the download directory (default: zh-TW)",
    )

    parser.add_argument(
        "--version",
        "-v",
        action="store_true",
        help="Show package version",
    )

    args = parser.parse_args()

    if args.version:
        print(__version__)
        sys.exit(0)

    if not args.inputs:
        parser.error("the following arguments are required: inputs")

    return args
