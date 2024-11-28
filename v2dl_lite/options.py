import sys
import logging
import argparse
from pathlib import Path

from .constant import BASE_DIR
from .utils import get_system_config_dir
from .version import __version__


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, prog) -> None:  # type: ignore
        super().__init__(prog, max_help_position=36)

    def _format_action_invocation(self, action):  # type: ignore
        if not action.option_strings:
            (metavar,) = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts = []
            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            # change to
            #    -s, --long ARGS
            else:
                default = action.dest.upper()
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    # parts.append('%s %s' % (option_string, args_string))
                    parts.append(f"{option_string}")
                parts[-1] += f" {args_string}"
            return ", ".join(parts)


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
        "--force",
        "-f",
        action="store_true",
        help="Force downloading, not skipping downloaded albums",
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
        "--log-level",
        default=2,
        type=int,
        choices=range(1, 6),
        help="Set log level from low to high (1~5)",
    )

    parser.add_argument(
        "--version",
        "-v",
        action="store_true",
        help="Show package version",
    )

    args = parser.parse_args()

    if args.version:
        print(__version__)  # noqa: T201
        sys.exit(0)

    if not args.inputs:
        parser.error("the following arguments are required: inputs")

    if args.log_level is not None:
        log_level_mapping = {
            1: logging.DEBUG,
            2: logging.INFO,
            3: logging.WARNING,
            4: logging.WARNING,
            5: logging.CRITICAL,
        }
        args.log_level = log_level_mapping.get(args.log_level, logging.INFO)

    return args
