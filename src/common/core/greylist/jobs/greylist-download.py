#!/usr/bin/env python3

from contextlib import suppress
from ipaddress import ip_address, ip_network
from os import _exit, getenv, sep
from os.path import join, normpath
from pathlib import Path
from re import IGNORECASE, compile as re_compile
from sys import exit as sys_exit, path as sys_path
from traceback import format_exc
from typing import Tuple

for deps_path in [join(sep, "usr", "share", "bunkerweb", *paths) for paths in (("deps", "python"), ("utils",), ("db",))]:
    if deps_path not in sys_path:
        sys_path.append(deps_path)

from requests import get

from Database import Database  # type: ignore
from logger import setup_logger  # type: ignore
from jobs import cache_file, cache_hash, del_file_in_db, is_cached_file, file_hash

rdns_rx = re_compile(rb"^[^ ]+$", IGNORECASE)
asn_rx = re_compile(rb"^\d+$")
uri_rx = re_compile(rb"^/")


def check_line(kind: str, line: bytes) -> Tuple[bool, bytes]:
    if kind == "IP":
        if b"/" in line:
            with suppress(ValueError):
                ip_network(line.decode("utf-8"))
                return True, line
        else:
            with suppress(ValueError):
                ip_address(line.decode("utf-8"))
                return True, line
    elif kind == "RDNS":
        if rdns_rx.match(line):
            return True, line.lower()
    elif kind == "ASN":
        real_line = line.replace(b"AS", b"").replace(b"as", b"")
        if asn_rx.match(real_line):
            return True, real_line
    elif kind == "USER_AGENT":
        return True, b"(?:\\b)" + line + b"(?:\\b)"
    elif kind == "URI":
        if uri_rx.match(line):
            return True, line

    return False, b""


logger = setup_logger("GREYLIST", getenv("LOG_LEVEL", "INFO"))
status = 0

try:
    # Check if at least a server has Greylist activated
    greylist_activated = False
    # Multisite case
    if getenv("MULTISITE", "no") == "yes":
        for first_server in getenv("SERVER_NAME", "").split(" "):
            if getenv(f"{first_server}_USE_GREYLIST", getenv("USE_GREYLIST", "no")) == "yes":
                greylist_activated = True
                break
    # Singlesite case
    elif getenv("USE_GREYLIST", "no") == "yes":
        greylist_activated = True

    if not greylist_activated:
        logger.info("Greylist is not activated, skipping downloads...")
        _exit(0)

    db = Database(logger, sqlalchemy_string=getenv("DATABASE_URI", None), pool=False)

    # Create directories if they don't exist
    greylist_path = Path(sep, "var", "cache", "bunkerweb", "greylist")
    greylist_path.mkdir(parents=True, exist_ok=True)
    tmp_greylist_path = Path(sep, "var", "tmp", "bunkerweb", "greylist")
    tmp_greylist_path.mkdir(parents=True, exist_ok=True)

    # Get URLs
    urls = {"IP": [], "RDNS": [], "ASN": [], "USER_AGENT": [], "URI": []}
    for kind in urls:
        for url in getenv(f"GREYLIST_{kind}_URLS", "").split(" "):
            if url and url not in urls[kind]:
                urls[kind].append(url)

    # Don't go further if the cache is fresh
    kinds_fresh = {
        "IP": True,
        "RDNS": True,
        "ASN": True,
        "USER_AGENT": True,
        "URI": True,
    }
    all_fresh = True
    for kind in kinds_fresh:
        if not is_cached_file(greylist_path.joinpath(f"{kind}.list"), "hour", db):
            kinds_fresh[kind] = False
            all_fresh = False
            logger.info(
                f"Greylist for {kind} is not cached, processing downloads..",
            )
        else:
            logger.info(
                f"Greylist for {kind} is already in cache, skipping downloads...",
            )
            if not urls[kind]:
                logger.warning(
                    f"Greylist for {kind} is cached but no URL is configured, removing from cache...",
                )
                greylist_path.joinpath(f"{kind}.list").unlink(missing_ok=True)
                deleted, err = del_file_in_db(f"{kind}.list", db)
                if not deleted:
                    logger.warning(f"Couldn't delete {kind}.list from cache : {err}")

    if all_fresh:
        _exit(0)

    # Loop on kinds
    for kind, urls_list in urls.items():
        if kinds_fresh[kind]:
            continue
        # Write combined data of the kind to a single temp file
        for url in urls_list:
            try:
                logger.info(f"Downloading greylist data from {url} ...")
                if url.startswith("file://"):
                    with open(normpath(url[7:]), "rb") as f:
                        iterable = f.readlines()
                else:
                    resp = get(url, stream=True, timeout=10)

                    if resp.status_code != 200:
                        logger.warning(f"Got status code {resp.status_code}, skipping...")
                        continue

                    iterable = resp.iter_lines()

                i = 0
                content = b""
                for line in iterable:
                    line = line.strip()

                    if not line or line.startswith((b"#", b";")):
                        continue
                    elif kind != "USER_AGENT":
                        line = line.split(b" ")[0]

                    ok, data = check_line(kind, line)
                    if ok:
                        content += data + b"\n"
                        i += 1

                tmp_greylist_path.joinpath(f"{kind}.list").write_bytes(content)

                logger.info(f"Downloaded {i} bad {kind}")
                # Check if file has changed
                new_hash = file_hash(tmp_greylist_path.joinpath(f"{kind}.list"))
                old_hash = cache_hash(greylist_path.joinpath(f"{kind}.list"), db)
                if new_hash == old_hash:
                    logger.info(
                        f"New file {kind}.list is identical to cache file, reload is not needed",
                    )
                else:
                    logger.info(
                        f"New file {kind}.list is different than cache file, reload is needed",
                    )
                    # Put file in cache
                    cached, err = cache_file(
                        tmp_greylist_path.joinpath(f"{kind}.list"),
                        greylist_path.joinpath(f"{kind}.list"),
                        new_hash,
                        db,
                    )

                    if not cached:
                        logger.error(f"Error while caching greylist : {err}")
                        status = 2
                    else:
                        status = 1
            except:
                status = 2
                logger.error(f"Exception while getting greylist from {url} :\n{format_exc()}")

except:
    status = 2
    logger.error(f"Exception while running greylist-download.py :\n{format_exc()}")

sys_exit(status)
