#!/usr/bin/env python3
"""
Download UTV images for the first 100 search queries in utv-search-queries.csv.

What it does:
- Reads the first 100 non-empty query rows.
- Supports common query-column names (query, search_query, search term, keyword, etc.).
- Falls back to the first CSV column if there is no recognized header.
- Searches both Medium and Large image results with DDGS.
- Keeps paging until the search backend stops returning new image URLs.
- Downloads valid images and converts them to .jpg.
- Skips small images, duplicate URLs, and duplicate image content.
- Saves everything into ./utv-images.
- Writes ./utv-images/download-log.csv so the job can be resumed.

Install:
    py -m pip install -U ddgs requests pillow

Run:
    py download_utv_images.py

Optional:
    py download_utv_images.py --csv path/to/utv-search-queries.csv --output path/to/utv-images
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import time
from pathlib import Path
from typing import Iterable

import requests
from ddgs import DDGS
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

ImageFile.LOAD_TRUNCATED_IMAGES = True

DEFAULT_CSV = "utv-search-queries.csv"
DEFAULT_OUTPUT = "utv-images"
QUERY_LIMIT = 100

# Medium/large image guardrails. Change these if you want smaller images too.
MIN_LONG_SIDE = 800
MIN_SHORT_SIDE = 450

SEARCH_SIZES = ("Medium", "Large")
RESULTS_PER_PAGE = 100

REQUEST_TIMEOUT = 20
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
SEARCH_DELAY_SECONDS = 0.75
QUERY_DELAY_SECONDS = 1.0
SEARCH_RETRIES = 3

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)

QUERY_COLUMN_NAMES = {
    "query",
    "search query",
    "search_query",
    "search term",
    "search_term",
    "keyword",
    "keywords",
    "term",
    "phrase",
}


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def slugify(value: str, max_length: int = 70) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value[:max_length].rstrip("-") or "utv")


def load_queries(csv_path: Path, limit: int = QUERY_LIMIT) -> list[str]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path.resolve()}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)

        # Safely detect only normal CSV-style delimiters.
        # csv.Sniffer can occasionally return an invalid delimiter for unusual
        # content, causing: ValueError: bad delimiter value
        delimiter = ","
        try:
            sniffed = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            candidate = getattr(sniffed, "delimiter", ",")
            if candidate in {",", ";", "\t", "|"}:
                delimiter = candidate
        except (csv.Error, ValueError, TypeError):
            # Fall back to a normal comma-separated CSV.
            delimiter = ","

        rows = list(csv.reader(f, delimiter=delimiter))

    rows = [row for row in rows if row and any(cell.strip() for cell in row)]
    if not rows:
        return []

    first_row = [normalize_header(cell) for cell in rows[0]]
    query_col = None

    for i, cell in enumerate(first_row):
        if cell in QUERY_COLUMN_NAMES:
            query_col = i
            break

    if query_col is not None:
        data_rows = rows[1:]
    else:
        query_col = 0
        data_rows = rows

    queries: list[str] = []
    for row in data_rows:
        if query_col >= len(row):
            continue
        query = row[query_col].strip()
        if not query:
            continue
        queries.append(query)
        if len(queries) >= limit:
            break

    return queries


def open_log(log_path: Path):
    log_exists = log_path.exists()
    fh = log_path.open("a", encoding="utf-8", newline="")
    writer = csv.writer(fh)

    if not log_exists:
        writer.writerow(
            [
                "query_row",
                "query",
                "image_url",
                "source_page",
                "width",
                "height",
                "filename",
                "sha256",
            ]
        )
        fh.flush()

    return fh, writer


def load_resume_state(log_path: Path) -> tuple[set[str], set[str]]:
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()

    if not log_path.exists():
        return seen_urls, seen_hashes

    try:
        with log_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = (row.get("image_url") or "").strip()
                digest = (row.get("sha256") or "").strip()
                if url:
                    seen_urls.add(url)
                if digest:
                    seen_hashes.add(digest)
    except Exception:
        # A damaged log should not prevent the downloader from running.
        pass

    return seen_urls, seen_hashes


def search_image_results(query: str) -> list[dict]:
    """
    Search Medium and Large images, paging until a page returns no new image URLs.
    """
    ddgs = DDGS(timeout=15)
    found: list[dict] = []
    seen_urls: set[str] = set()

    for image_size in SEARCH_SIZES:
        page = 1

        while True:
            results = None

            for attempt in range(1, SEARCH_RETRIES + 1):
                try:
                    results = ddgs.images(
                        query=query,
                        region="us-en",
                        safesearch="moderate",
                        max_results=RESULTS_PER_PAGE,
                        page=page,
                        size=image_size,
                    )
                    break
                except Exception as exc:
                    if attempt == SEARCH_RETRIES:
                        print(
                            f"    Search stopped for {image_size}, page {page}: {exc}"
                        )
                    else:
                        time.sleep(attempt * 2.0)

            if not results:
                break

            new_count = 0
            for result in results:
                image_url = (result.get("image") or "").strip()
                if not image_url or image_url in seen_urls:
                    continue

                seen_urls.add(image_url)
                result["_search_size"] = image_size
                found.append(result)
                new_count += 1

            print(
                f"    {image_size} page {page}: "
                f"{len(results)} results, {new_count} new"
            )

            # Some backends repeat the last page forever. Stop when that happens.
            if new_count == 0:
                break

            page += 1
            time.sleep(SEARCH_DELAY_SECONDS)

    return found


def read_response_bytes(response: requests.Response) -> bytes:
    data = bytearray()

    for chunk in response.iter_content(chunk_size=128 * 1024):
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("image exceeded maximum download size")

    return bytes(data)


def image_to_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)

    # Animated files: use the first frame.
    try:
        image.seek(0)
    except EOFError:
        pass

    if image.mode in ("RGBA", "LA"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background

    if image.mode == "P" and "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background

    return image.convert("RGB")


def is_large_enough(width: int, height: int) -> bool:
    long_side = max(width, height)
    short_side = min(width, height)
    return long_side >= MIN_LONG_SIDE and short_side >= MIN_SHORT_SIDE


def download_one(
    session: requests.Session,
    result: dict,
    query: str,
    query_number: int,
    output_dir: Path,
    seen_urls: set[str],
    seen_hashes: set[str],
) -> tuple[str, dict | None]:
    image_url = (result.get("image") or "").strip()
    source_page = (result.get("url") or "").strip()

    if not image_url:
        return "no-url", None

    if image_url in seen_urls:
        return "seen-url", None

    try:
        response = session.get(
            image_url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            return "not-image", None

        raw = read_response_bytes(response)
        if not raw:
            return "empty", None

        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_hashes:
            seen_urls.add(image_url)
            return "duplicate", None

        with Image.open(io.BytesIO(raw)) as opened:
            opened.load()
            image = image_to_rgb(opened)

        width, height = image.size
        if not is_large_enough(width, height):
            seen_urls.add(image_url)
            return "too-small", None

        url_id = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:10]
        filename = (
            f"{query_number:03d}_{slugify(query)}_{url_id}.jpg"
        )
        destination = output_dir / filename

        # Extremely unlikely, but avoid overwriting an unrelated file.
        suffix = 2
        while destination.exists():
            destination = output_dir / (
                f"{query_number:03d}_{slugify(query)}_{url_id}_{suffix}.jpg"
            )
            suffix += 1

        image.save(
            destination,
            format="JPEG",
            quality=92,
            optimize=True,
            progressive=True,
        )

        seen_urls.add(image_url)
        seen_hashes.add(digest)

        return "saved", {
            "image_url": image_url,
            "source_page": source_page,
            "width": width,
            "height": height,
            "filename": destination.name,
            "sha256": digest,
        }

    except (
        requests.RequestException,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        return f"error: {exc}", None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download UTV images for the first 100 CSV search queries."
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV,
        help=f"CSV file path (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output folder (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    queries = load_queries(csv_path, QUERY_LIMIT)
    if not queries:
        print("No search queries were found in the CSV.")
        return 1

    log_path = output_dir / "download-log.csv"
    seen_urls, seen_hashes = load_resume_state(log_path)
    log_fh, log_writer = open_log(log_path)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    total_saved = 0
    total_skipped = 0
    total_errors = 0

    try:
        print(f"Loaded {len(queries)} queries from: {csv_path.resolve()}")
        print(f"Saving images to: {output_dir.resolve()}")
        print(
            f"Minimum image size: long side >= {MIN_LONG_SIDE}px and "
            f"short side >= {MIN_SHORT_SIDE}px"
        )
        print()

        for query_number, query in enumerate(queries, start=1):
            print(f"[{query_number}/{len(queries)}] {query}")

            try:
                results = search_image_results(query)
            except Exception as exc:
                print(f"    Search failed: {exc}")
                total_errors += 1
                continue

            print(f"    Unique image URLs found: {len(results)}")

            saved_this_query = 0
            skipped_this_query = 0
            errors_this_query = 0

            for result in results:
                status, info = download_one(
                    session=session,
                    result=result,
                    query=query,
                    query_number=query_number,
                    output_dir=output_dir,
                    seen_urls=seen_urls,
                    seen_hashes=seen_hashes,
                )

                if status == "saved" and info:
                    saved_this_query += 1
                    total_saved += 1
                    log_writer.writerow(
                        [
                            query_number,
                            query,
                            info["image_url"],
                            info["source_page"],
                            info["width"],
                            info["height"],
                            info["filename"],
                            info["sha256"],
                        ]
                    )
                    log_fh.flush()
                elif status.startswith("error:"):
                    errors_this_query += 1
                    total_errors += 1
                else:
                    skipped_this_query += 1
                    total_skipped += 1

            print(
                f"    Saved: {saved_this_query} | "
                f"Skipped: {skipped_this_query} | "
                f"Errors: {errors_this_query}"
            )
            print()

            time.sleep(QUERY_DELAY_SECONDS)

    except KeyboardInterrupt:
        print("\nStopped by user. Run the script again to resume.")
    finally:
        log_fh.close()
        session.close()

    print("Finished.")
    print(f"Downloaded: {total_saved}")
    print(f"Skipped:    {total_skipped}")
    print(f"Errors:     {total_errors}")
    print(f"Folder:     {output_dir.resolve()}")
    print(f"Log:        {log_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
