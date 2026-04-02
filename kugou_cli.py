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
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_LIMIT = 30
DEFAULT_OUTPUT_DIR = Path("downloads")
DOWNLOAD_CHUNK_SIZE = 64 * 1024
SEARCH_URL = (
    "http://mobilecdn.kugou.com/api/v3/search/song"
    "?format=json&keyword={keyword}&page=1&pagesize={page_size}"
)
ALBUM_INFO_URL = "http://mobilecdn.kugou.com/api/v3/album/info?albumid={album_id}&format=json"
ALBUM_SONGS_URL = (
    "http://mobilecdn.kugou.com/api/v3/album/song"
    "?albumid={album_id}&page=1&pagesize={page_size}&format=json"
)
TRACK_URL = (
    "http://trackercdn.kugou.com/i/"
    "?cmd=4&hash={hash_value}&key={key}&pid=1&forceDown=0&vip=1"
)
USER_AGENT = "Mozilla/5.0 (compatible; kugou-cli/1.0)"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
MIXSONG_DATA_RE = re.compile(r"var\s+dataFromSmarty\s*=\s*(\[.*?\])\s*,\s*//", re.DOTALL)
MIXSONG_PATH_RE = re.compile(r"/mixsong/([a-z0-9]+)", re.IGNORECASE)
ALBUM_PATH_RE = re.compile(r"/album/info/([a-z0-9]+)", re.IGNORECASE)


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
    album_id: str = ""
    source_label: str = ""

    @property
    def display_size_mb(self) -> float:
        return self.file_size / (1024 * 1024) if self.file_size else 0.0

    @property
    def display_duration(self) -> str:
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def display_bitrate(self) -> str:
        if not self.bitrate:
            return "unknown"
        try:
            bitrate_value = int(self.bitrate)
        except ValueError:
            return self.bitrate
        if bitrate_value >= 1000:
            return str(bitrate_value // 1000)
        return str(bitrate_value)


def safe_print(message: str, *, stream: Any = sys.stdout) -> None:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    print(message.encode(encoding, errors="replace").decode(encoding), file=stream)


def http_get_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace")


def http_get_json(url: str) -> dict[str, Any]:
    return json.loads(http_get_text(url))


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip().rstrip(". ")
    return cleaned or "track"


def is_probable_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def decode_base36_candidates(value: str) -> list[int]:
    normalized = value.lower()
    candidates: list[int] = []
    seen: set[int] = set()
    for cut in range(2, min(5, len(normalized))):
        core = normalized[:-cut]
        if not core:
            continue
        try:
            decoded = int(core, 36)
        except ValueError:
            continue
        if decoded not in seen:
            seen.add(decoded)
            candidates.append(decoded)
    try:
        decoded_full = int(normalized, 36)
    except ValueError:
        decoded_full = None
    if decoded_full is not None and decoded_full not in seen:
        candidates.append(decoded_full)
    return candidates


def extract_best_hash(item: dict[str, Any]) -> str:
    for key_name in ("sqhash", "320hash", "hash"):
        value = str(item.get(key_name) or "").strip()
        if value:
            return value
    return ""


def build_track_from_metadata(item: dict[str, Any], *, filename_fallback: str = "Unknown Track") -> Track | None:
    hash_value = extract_best_hash(item)
    if not hash_value:
        return None

    key = md5_hex(f"{hash_value}kgcloud")

    try:
        detail = http_get_json(TRACK_URL.format(hash_value=hash_value, key=key))
    except (HTTPError, URLError, json.JSONDecodeError):
        return None

    if str(detail.get("status")) != "1":
        return None

    download_url = str(detail.get("url") or "").replace("\\", "")
    if not download_url:
        return None

    filename = (
        str(item.get("filename") or "")
        or str(item.get("audio_name") or "")
        or filename_fallback
    )

    return Track(
        filename=filename,
        hash_value=hash_value,
        key=key,
        download_url=download_url,
        extension=str(detail.get("extName") or item.get("extname") or "flac").lower(),
        bitrate=str(detail.get("bitRate") or item.get("bitrate") or ""),
        file_size=int(detail.get("fileSize") or item.get("filesize") or 0),
        duration_seconds=int(detail.get("timeLength") or item.get("duration") or item.get("timelength") or 0),
        album_id=str(item.get("album_id") or ""),
    )


def search_tracks(keyword: str, page_size: int = DEFAULT_LIMIT) -> list[Track]:
    url = SEARCH_URL.format(keyword=quote(keyword), page_size=page_size)
    payload = http_get_json(url)

    results: list[Track] = []
    for item in payload.get("data", {}).get("info", []):
        if not isinstance(item, dict):
            continue
        track = build_track_from_metadata(item)
        if track is not None:
            results.append(track)

    return results


def resolve_mixsong_url(url: str) -> list[Track]:
    html = http_get_text(url)
    match = MIXSONG_DATA_RE.search(html)
    if not match:
        raise ValueError("Unable to extract song data from mixsong page.")

    items = json.loads(match.group(1))
    results: list[Track] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        track = build_track_from_metadata(item)
        if track is not None:
            results.append(track)

    return results


def resolve_album_url(url: str, page_size: int = 100) -> list[Track]:
    match = ALBUM_PATH_RE.search(urlparse(url).path)
    if not match:
        raise ValueError("Album URL did not contain an encoded album id.")

    encoded_album_id = match.group(1)
    found_album_tracks = False

    for decoded_album_id in decode_base36_candidates(encoded_album_id):
        album_id = str(decoded_album_id)
        album_info = http_get_json(ALBUM_INFO_URL.format(album_id=album_id))
        album_info_data = album_info.get("data") if isinstance(album_info.get("data"), dict) else {}
        album_name = str(album_info_data.get("albumname") or "Unknown Album")

        songs_payload = http_get_json(ALBUM_SONGS_URL.format(album_id=album_id, page_size=page_size))
        song_data = songs_payload.get("data") if isinstance(songs_payload.get("data"), dict) else {}
        info = song_data.get("info", [])
        if info:
            found_album_tracks = True

        results: list[Track] = []
        for item in info:
            if not isinstance(item, dict):
                continue
            track = build_track_from_metadata(item, filename_fallback=album_name)
            if track is not None:
                results.append(track)

        if results:
            return results

    if found_album_tracks:
        raise ValueError("Album found, but all tracks appear to require payment or are otherwise unavailable.")

    return []


def resolve_input(value: str, *, page_size: int = DEFAULT_LIMIT) -> list[Track]:
    if not is_probable_url(value):
        return search_tracks(value, page_size)

    path = urlparse(value).path.lower()
    if MIXSONG_PATH_RE.search(path):
        return resolve_mixsong_url(value)
    if ALBUM_PATH_RE.search(path):
        return resolve_album_url(value, page_size=max(page_size, 100))

    raise ValueError("Unsupported Kugou URL. Supported: mixsong and album/info URLs.")


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
    results = resolve_input(args.keyword, page_size=args.limit)
    print_results(results)
    return 0


def command_download(args: argparse.Namespace) -> int:
    results = resolve_input(args.keyword, page_size=args.limit)
    if not results:
        safe_print("No downloadable results found.")
        return 1

    print_results(results)

    parsed_path = urlparse(args.keyword).path.lower() if is_probable_url(args.keyword) else ""
    is_album_input = bool(ALBUM_PATH_RE.search(parsed_path))
    is_mixsong_input = bool(MIXSONG_PATH_RE.search(parsed_path))
    if args.index:
        selected_indexes = validate_indexes(args.index, len(results))
    elif is_album_input or is_mixsong_input:
        selected_indexes = list(range(1, len(results) + 1))
    else:
        raise ValueError("--index is required unless the input is a supported direct Kugou URL.")

    for index in selected_indexes:
        track = results[index - 1]
        destination = resolve_output_path(Path(args.output), track)
        safe_print(f"Downloading [{index}] -> {destination}")
        download_file(track.download_url, destination)

    return 0


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("keyword", help="Song name, artist, search phrase, or supported Kugou URL.")
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

    search_parser = subparsers.add_parser("search", help="Search for downloadable tracks or inspect a supported Kugou URL.")
    add_common_arguments(search_parser)
    search_parser.set_defaults(func=command_search)

    download_parser = subparsers.add_parser("download", help="Search or resolve a supported Kugou URL, then download selected tracks.")
    add_common_arguments(download_parser)
    download_parser.add_argument(
        "--index",
        type=int,
        nargs="+",
        help="One or more result numbers from the search list. Optional for direct Kugou song or album URLs; defaults to all resolved tracks.",
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
        safe_print("Failed to parse Kugou response.", stream=sys.stderr)
        return 1
    except ValueError as exc:
        safe_print(str(exc), stream=sys.stderr)
        return 1
    except KeyboardInterrupt:
        safe_print("Cancelled.", stream=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
