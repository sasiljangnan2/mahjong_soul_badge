import asyncio
import json
import logging
import sys
from optparse import OptionParser

from majsoul_client import fetch_summary


def setup_logging(log_file=None, quiet=False):
    log_format = "%(asctime)s %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = []
    console_level = logging.WARNING if quiet else logging.INFO
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    handlers.append(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )


async def main():
    parser = OptionParser()
    parser.add_option("-u", "--username", type="string", help="Login account.")
    parser.add_option("-p", "--password", type="string", help="Login password.")
    parser.add_option("--target-nickname", type="string", help="Target nickname.")
    parser.add_option("-n", "--recent-count", type="int", default=10, help="Recent count for each (3p/4p).")
    parser.add_option("--quiet", action="store_true", help="Show only warnings/errors in terminal.")
    parser.add_option("--log-file", type="string", help="Write detailed logs to a file.")

    opts, _ = parser.parse_args()
    setup_logging(log_file=opts.log_file, quiet=opts.quiet)

    username = opts.username
    password = opts.password
    if not username or not password:
        parser.error("Username and password are required")

    summary = await fetch_summary(
        username=username,
        password=password,
        target_nickname=opts.target_nickname,
        recent_count=opts.recent_count,
    )
    logging.info("%s", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
