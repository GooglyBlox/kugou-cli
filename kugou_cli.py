#!/usr/bin/env python3
"""Simple Kugou music search and download CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_LIMIT = 30
DEFAULT_OUTPUT_DIR = Path("downloads")
DOWNLOAD_CHUNK_SIZE = 64 * 1024
SEARCH_URL = (
    "http://mobilecdn.kugou.com/api/v3/search/song"
    "?format=json&keyword={keyword}&page=1&pagesize={page_size}"
)
TRACK_URL = (
    "http://trackercdn.kugou.com/i/"
    "?cmd=4&hash={hash_value}&key={key}&pid=1&forceDown=0&vip=1"
)
USER_AGENT = "Mozilla/5.0 (compatible; kugou-cli/1.0)"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


@dataclass(frozen=True)
class Track:
    filename: str
    hash_value: str
    key: str
    download_url: str
    extension: str
    bitrate: str
    file_size: int
    duration_seconds: int

    @property
    def display_size_mb(self) -> float:
        return self.file_size / (1024 * 1024) if self.file_size else 0.0

    @property
    def display_duration(self) -> str:
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def display_bitrate(self) -> str:
        return self.bitrate or "unknown"


def safe_print(message: str, *, stream: Any = sys.stdout) -> None:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    print(message.encode(encoding, errors="replace").decode(encoding), file=stream)


def http_get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip().rstrip(". ")
    return cleaned or "track"


def parse_track(item: dict[str, Any]) -> Track | None:
    sqhash = str(item.get("sqhash") or "")
    if not sqhash:
        return None

    key = md5_hex(f"{sqhash}kgcloud")

    try:
        detail = http_get_json(TRACK_URL.format(hash_value=sqhash, key=key))
    except (HTTPError, URLError, json.JSONDecodeError):
        return None

    if str(detail.get("status")) != "1":
        return None

    download_url = str(detail.get("url") or "").replace("\\", "")
    if not download_url:
        return None

    return Track(
        filename=str(item.get("filename") or "Unknown Track"),
        hash_value=sqhash,
        key=key,
        download_url=download_url,
        extension=str(detail.get("extName") or "flac").lower(),
        bitrate=str(detail.get("bitRate") or ""),
        file_size=int(detail.get("fileSize") or 0),
        duration_seconds=int(detail.get("timeLength") or 0),
    )


def search_tracks(keyword: str, page_size: int = DEFAULT_LIMIT) -> list[Track]:
    url = SEARCH_URL.format(keyword=quote(keyword), page_size=page_size)
    payload = http_get_json(url)

    results: list[Track] = []
    for item in payload.get("data", {}).get("info", []):
        if not isinstance(item, dict):
            continue
        track = parse_track(item)
        if track is not None:
            results.append(track)

    return results


def print_results(results: Iterable[Track]) -> None:
    printed_any = False
    for index, track in enumerate(results, start=1):
        printed_any = True
        safe_print(
            f"[{index}] {track.filename} | {track.display_bitrate} kbps | "
            f".{track.extension} | {track.display_size_mb:.2f} MB | "
            f"{track.display_duration}"
        )

    if not printed_any:
        safe_print("No downloadable results found.")


def download_file(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request) as response, destination.open("wb") as output:
        while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
            output.write(chunk)


def resolve_output_path(output_dir: Path, track: Track) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = sanitize_filename(track.filename)
    extension = track.extension or "flac"
    candidate = output_dir / f"{basename}.{extension}"
    suffix = 2

    while candidate.exists():
        candidate = output_dir / f"{basename} ({suffix}).{extension}"
        suffix += 1

    return candidate


def validate_indexes(indexes: Iterable[int], total: int) -> list[int]:
    valid: list[int] = []
    seen: set[int] = set()

    for index in indexes:
        if index in seen:
            continue
        seen.add(index)

        if 1 <= index <= total:
            valid.append(index)
        else:
            safe_print(f"Skipping invalid selection: {index}", stream=sys.stderr)

    return sorted(valid)


def command_search(args: argparse.Namespace) -> int:
    results = search_tracks(args.keyword, args.limit)
    print_results(results)
    return 0


def command_download(args: argparse.Namespace) -> int:
    results = search_tracks(args.keyword, args.limit)
    if not results:
        safe_print("No downloadable results found.")
        return 1

    print_results(results)

    for index in validate_indexes(args.index, len(results)):
        track = results[index - 1]
        destination = resolve_output_path(Path(args.output), track)
        safe_print(f"Downloading [{index}] -> {destination}")
        download_file(track.download_url, destination)

    return 0


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("keyword", help="Song or artist search term.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Max search results to inspect.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and download music from the command line."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search for downloadable tracks.")
    add_common_arguments(search_parser)
    search_parser.set_defaults(func=command_search)

    download_parser = subparsers.add_parser("download", help="Search and download selected tracks.")
    add_common_arguments(download_parser)
    download_parser.add_argument(
        "--index",
        type=int,
        nargs="+",
        required=True,
        help="One or more result numbers from the search list.",
    )
    download_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to save downloaded files into.",
    )
    download_parser.set_defaults(func=command_download)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except HTTPError as exc:
        safe_print(f"HTTP error: {exc.code} {exc.reason}", stream=sys.stderr)
        return 1
    except URLError as exc:
        safe_print(f"Network error: {exc.reason}", stream=sys.stderr)
        return 1
    except json.JSONDecodeError:
        safe_print(f"Failed to parse Kugou response.", stream=sys.stderr)
        return 1
    except KeyboardInterrupt:
        safe_print("Cancelled.", stream=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())