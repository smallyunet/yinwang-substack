from __future__ import annotations

import argparse
import html as html_std
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from _util import (
    ensure_dir,
    env_http_config,
    ext_from_content_type,
    guess_ext_from_url,
    http_get_bytes,
    http_get_json,
    make_session,
    polite_sleep,
    sha256_hex,
    write_json,
)


def parse_image_urls_from_body_html(body_html: str) -> list[str]:
    if not body_html:
        return []
    soup = BeautifulSoup(body_html, "lxml")
    urls: list[str] = []

    def best_from_srcset(srcset: str) -> str | None:
        if not srcset:
            return None
        best_url = None
        best_w = -1
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^(\S+)\s+(\d+)w$", part)
            if m:
                u, w = m.group(1), int(m.group(2))
                if w > best_w:
                    best_url, best_w = u, w
            else:
                u = part.split()[0]
                if not best_url:
                    best_url = u
        return best_url

    # Substack images often appear as:
    # - <a class="image-link ..." href="https://substackcdn.com/image/fetch/...">
    # - <img ... data-attrs='{"src":"https://substack-post-media.s3..." ...}'>
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        cls = " ".join(a.get("class") or [])
        if (
            "image" in cls
            or "image-link" in cls
            or "substackcdn.com/image" in href
            or "substack-post-media" in href
        ):
            urls.append(href)

    # Some posts use <picture><source srcset=...></picture>
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        best_url = best_from_srcset(srcset) if srcset else None
        if best_url:
            urls.append(best_url)

    for img in soup.find_all("img"):
        data_attrs = img.get("data-attrs")
        if data_attrs:
            # data-attrs might be HTML-escaped JSON
            for candidate in (data_attrs, html_std.unescape(data_attrs)):
                try:
                    obj = json.loads(candidate)
                except Exception:
                    continue
                src0 = obj.get("src")
                if isinstance(src0, str) and src0:
                    urls.append(src0)
                    break

        src = img.get("src")
        if src:
            urls.append(src)
        # substack often uses srcset
        srcset = img.get("srcset")
        if srcset:
            best_url = best_from_srcset(srcset)
            if best_url:
                urls.append(best_url)
    # dedupe but preserve order
    seen = set()
    out: list[str] = []
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


_HTTP_URL_RE = re.compile(r"https?://[^\s\"\'<>]+", re.IGNORECASE)
_ENC_HTTP_URL_RE = re.compile(r"https?%3A%2F%2F[^\s\"\'<>]+", re.IGNORECASE)
_TRAILING_PUNCT = ")]}\"'>.,”’"


def normalize_image_download_url(raw_url: str, base_url: str) -> str | None:
    """Normalize a raw URL-ish string into a real http(s) URL.

    Substack sometimes embeds Cloudinary transformation segments like
    `fl_progressive:steep/https%3A%2F%2F...` which are not valid URLs for requests.
    We try to extract and decode the embedded encoded URL.
    """
    if not raw_url:
        return None
    s = html_std.unescape(str(raw_url)).strip()
    if not s:
        return None
    if s.startswith("data:"):
        return None
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("http://") or s.startswith("https://"):
        return s

    # If the string contains a real URL somewhere, extract it.
    m = _HTTP_URL_RE.search(s)
    if m:
        return m.group(0).rstrip(_TRAILING_PUNCT)

    # Common Substack/Cloudinary pattern: transform/.../https%3A%2F%2F...
    m2 = _ENC_HTTP_URL_RE.search(s)
    if m2:
        decoded = unquote(m2.group(0)).strip().rstrip(_TRAILING_PUNCT)
        if decoded.startswith("http://") or decoded.startswith("https://"):
            return decoded

    # Relative URL fallback.
    if s.startswith("/"):
        return urljoin(base_url.rstrip("/") + "/", s)

    return None


def fetch_archive(sess, base_url: str, timeout_s: int, limit: int | None = None) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    offset = 0
    page_limit = 50
    while True:
        url = f"{base_url}/api/v1/archive?sort=new&offset={offset}&limit={page_limit}"
        batch = http_get_json(sess, url, timeout_s=timeout_s)
        if not isinstance(batch, list) or not batch:
            break
        posts.extend(batch)
        offset += len(batch)
        if limit is not None and len(posts) >= limit:
            posts = posts[:limit]
            break
    return posts


def download_image(sess, url: str, dest_path: Path, timeout_s: int, *, retries: int = 2) -> str:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            data, content_type = http_get_bytes(sess, url, timeout_s=timeout_s)
            ext = guess_ext_from_url(url) or ext_from_content_type(content_type) or ".bin"
            final_path = dest_path.with_suffix(ext)
            ensure_dir(final_path.parent)
            final_path.write_bytes(data)
            return final_path.name
        except Exception as e:  # noqa: BLE001 - want to keep crawling
            last_exc = e
            # small backoff; avoid hammering
            if attempt < retries:
                continue
    assert last_exc is not None
    raise last_exc


def log(msg: str, *, quiet: bool) -> None:
    if quiet:
        return
    print(msg, file=sys.stderr, flush=True)


def shorten(text: str, n: int = 60) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="data/raw", help="raw data output dir")
    ap.add_argument("--limit", type=int, default=None, help="only fetch first N posts")
    ap.add_argument("--skip-media", action="store_true", help="do not download images")
    ap.add_argument("--quiet", action="store_true", help="suppress progress logs")
    args = ap.parse_args()

    cfg = env_http_config()
    raw_dir = Path(args.raw_dir)
    ensure_dir(raw_dir)

    sess = make_session(cfg)

    log(f"[1/2] Fetching archive list from {cfg.base_url}...", quiet=args.quiet)
    archive_posts = fetch_archive(sess, cfg.base_url, timeout_s=cfg.timeout_s, limit=args.limit)
    write_json(raw_dir / "archive.json", archive_posts)
    log(f"Archive posts: {len(archive_posts)}", quiet=args.quiet)

    total = len(archive_posts)
    try:
        for idx, item in enumerate(archive_posts, start=1):
            slug = item.get("slug")
            if not slug:
                continue

            title = item.get("title") or ""
            log(f"\n[2/2] ({idx}/{total}) Post {slug} - {shorten(title)}", quiet=args.quiet)

            post_dir = raw_dir / "posts" / slug
            ensure_dir(post_dir)

            post_json_path = post_dir / "post.json"
            body_html_path = post_dir / "body.html"
            media_dir = post_dir / "media"

            post_url = f"{cfg.base_url}/api/v1/posts/{slug}"
            post = http_get_json(sess, post_url, timeout_s=cfg.timeout_s)
            write_json(post_json_path, post)

            body_html = post.get("body_html") or ""
            body_html_path.write_text(body_html, encoding="utf-8")

            if not body_html:
                log("  body_html: empty (maybe paywalled or error)", quiet=args.quiet)

            if args.skip_media:
                log("  media: skipped (--skip-media)", quiet=args.quiet)
                polite_sleep(cfg)
                continue

            image_urls = parse_image_urls_from_body_html(body_html)
            cover = post.get("cover_image")
            if cover:
                image_urls.insert(0, cover)

            normalized_pairs: list[tuple[str, str]] = []
            skipped_invalid = 0
            for raw_u in image_urls:
                norm_u = normalize_image_download_url(raw_u, cfg.base_url)
                if not norm_u:
                    skipped_invalid += 1
                    continue
                normalized_pairs.append((raw_u, norm_u))

            if skipped_invalid:
                log(
                    f"  media: found {len(image_urls)} image urls (usable {len(normalized_pairs)}, skipped {skipped_invalid})",
                    quiet=args.quiet,
                )
            else:
                log(f"  media: found {len(image_urls)} image urls", quiet=args.quiet)

            media_map: dict[str, str] = {}
            failures: list[dict[str, str]] = []
            downloaded = 0
            cached = 0
            failed = 0
            failure_print_budget = 3

            for raw_u, download_u in normalized_pairs:
                # deterministic name by normalized download URL hash
                digest = sha256_hex(download_u)[:16]
                dest_stub = media_dir / digest
                # if already exists (any ext), skip
                existing = list(dest_stub.parent.glob(dest_stub.name + ".*"))
                if existing:
                    media_map[raw_u] = existing[0].name
                    cached += 1
                    continue
                try:
                    filename = download_image(sess, download_u, dest_stub, timeout_s=cfg.timeout_s, retries=2)
                    media_map[raw_u] = filename
                    downloaded += 1
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    failures.append(
                        {
                            "url": raw_u,
                            "download_url": download_u,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
                    if (not args.quiet) and failure_print_budget > 0:
                        log(f"  media: failed {shorten(raw_u, 90)} ({type(e).__name__})", quiet=False)
                        failure_print_budget -= 1
                    continue
                finally:
                    polite_sleep(cfg)

            write_json(post_dir / "media_map.json", media_map)
            if failures:
                write_json(post_dir / "media_failures.json", failures)

            log(f"  media: downloaded {downloaded}, cached {cached}, failed {failed}", quiet=args.quiet)
            polite_sleep(cfg)
    except KeyboardInterrupt:
        log("\nInterrupted (Ctrl+C). Progress up to last completed post is saved in data/raw.", quiet=False)
        raise


if __name__ == "__main__":
    main()
