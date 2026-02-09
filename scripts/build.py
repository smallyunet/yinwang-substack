from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from _util import ensure_dir, read_json


def iso_to_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = date_parser.isoparse(iso)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso


def rewrite_images(body_html: str, media_map: dict[str, str], rel_prefix: str) -> str:
    if not body_html:
        return ""
    soup = BeautifulSoup(body_html, "lxml")
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and src in media_map:
            img["src"] = f"{rel_prefix}{media_map[src]}"
        if img.get("srcset"):
            img.attrs.pop("srcset", None)
        img.attrs.pop("sizes", None)
        img.attrs.pop("loading", None)
    # soup wraps fragments with html/body; return inner
    if soup.body:
        return "".join(str(x) for x in soup.body.contents)
    return str(soup)


def render_page(
    title: str,
    subtitle: str,
    content_html: str,
    *,
    css_href: str,
    home_href: str,
    source_url: str | None,
    paid: bool,
) -> str:
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle) if subtitle else ""
    source_block = ""
    if source_url:
        safe_src = html.escape(source_url)
        source_block = f"<a class=\"source-link\" href=\"{safe_src}\" target=\"_blank\" rel=\"noopener noreferrer\">原文链接</a>"

    paid_tag = "<span class=\"tag tag-paid\">PAID</span>" if paid else ""

    meta_items: list[str] = []
    if safe_sub:
        meta_items.append(f"<span class=\"meta-date\">{safe_sub}</span>")
    if paid_tag:
        meta_items.append(paid_tag)
    if source_block:
        meta_items.append(source_block)
    meta_block = f"<div class=\"meta\">{''.join(meta_items)}</div>" if meta_items else ""

    paid_notice = ""
    if paid and source_url:
        safe_src = html.escape(source_url)
        paid_notice = (
            "<blockquote class=\"paid-note\">"
            "这是一篇付费文章，本地内容可能不完整。"
            f"<a href=\"{safe_src}\" target=\"_blank\" rel=\"noopener noreferrer\">点击跳转到原文查看</a>。"
            "</blockquote>"
        )
    return f"""<!doctype html>
<html lang=\"zh\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{safe_title}</title>
    <link rel=\"stylesheet\" href=\"{html.escape(css_href)}\" />
  </head>
  <body>
    <div class=\"container\">
      <header class=\"header\">
        <a class=\"home\" href=\"{html.escape(home_href)}\">Home</a>
      </header>
      <main>
                <h1>{safe_title}</h1>
                {meta_block}
                <article class=\"post\">{content_html}</article>
                {paid_notice}
      </main>
    </div>
  </body>
</html>"""


def render_index(items: list[dict]) -> str:
        li: list[str] = []
        for it in items:
                title = html.escape(it["title"])
                date = html.escape(it["date"])
                paid = bool(it.get("paid"))
                slug = it["slug"]
                paid_mark = "<span class=\"tag tag-paid\">PAID</span>" if paid else ""
                li.append(
            f"<li><a href=\"posts/{slug}/\">{title}</a><span class=\"date\">{date}</span>{paid_mark}</li>"
                )
        lis = "\n".join(li)
        return f"""<!doctype html>
<html lang=\"zh\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Archive</title>
    <link rel=\"stylesheet\" href=\"assets/style.css\" />
  </head>
  <body>
    <div class=\"container\">
      <main>
        <h1>Archive</h1>
        <ul class=\"index\">{lis}</ul>
      </main>
      <footer class=\"footer\">
        <p>免责声明：本网站仅为个人学习备份，原作者王垠。原站点：<a href=\"https://yinwang1.substack.com/\" target=\"_blank\" rel=\"noopener noreferrer\">https://yinwang1.substack.com/</a></p>
      </footer>
    </div>
  </body>
</html>"""


def write_style(site_dir: Path) -> None:
    css = """
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', 'Microsoft Yahei', sans-serif; line-height: 1.6; }
.container { max-width: 860px; margin: 0 auto; padding: 24px; }
.header { margin-bottom: 18px; }
.home { text-decoration: none; color: inherit; }
.meta { display: flex; gap: 12px; align-items: baseline; margin-top: 6px; margin-bottom: 16px; color: #666; }
.meta-date { color: #666; }
.source-link { color: #06c; text-decoration: none; }
.source-link:hover { text-decoration: underline; }
.paid-note { margin: 18px 0 0; padding: 10px 12px; border-left: 3px solid #ddd; background: #fafafa; color: #666; font-size: 0.95em; }
.paid-note a { color: #06c; text-decoration: none; }
.paid-note a:hover { text-decoration: underline; }
.index { list-style: none; padding-left: 0; }
.index li { display: flex; gap: 12px; align-items: baseline; padding: 6px 0; }
.index a { text-decoration: none; }
.tag { font-size: 0.75em; padding: 1px 6px; border-radius: 999px; border: 1px solid #ddd; color: #666; white-space: nowrap; }
.tag-paid { background: #f5f5f5; }
.date { color: #888; font-size: 0.9em; }
.post img { max-width: 100%; height: auto; }
.footer { margin-top: 48px; color: #888; font-size: 0.9em; }
"""
    assets = site_dir / "assets"
    ensure_dir(assets)
    (assets / "style.css").write_text(css.strip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--site-dir", default="docs")
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    site_dir = Path(args.site_dir)

    if site_dir.exists():
        shutil.rmtree(site_dir)
    ensure_dir(site_dir)
    # disable Jekyll on GitHub Pages (we are already generating plain HTML)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    write_style(site_dir)

    archive: list[dict] = []
    archive_path = raw_dir / "archive.json"
    if archive_path.exists():
        try:
            tmp = read_json(archive_path)
            if isinstance(tmp, list):
                archive = [a for a in tmp if isinstance(a, dict)]
        except Exception:
            archive = []
    archive_by_slug = {a.get("slug"): a for a in archive if a.get("slug")}

    # Prefer scanning what we actually have in raw_dir/posts so build doesn't depend on archive.json size.
    posts_root = raw_dir / "posts"
    slugs: list[str] = []
    if posts_root.exists():
        for p in posts_root.iterdir():
            if p.is_dir():
                slugs.append(p.name)

    items: list[dict] = []
    for slug in slugs:
        post_dir = posts_root / slug
        post_json_path = post_dir / "post.json"
        body_path = post_dir / "body.html"
        if not post_json_path.exists() or not body_path.exists():
            continue
        post = read_json(post_json_path)
        a = archive_by_slug.get(slug) or {}
        post_date = post.get("post_date") or a.get("post_date") or ""
        items.append({"slug": slug, "post": post, "post_date": post_date})

    def sort_key(it: dict) -> str:
        return it.get("post_date") or ""

    items_sorted = sorted(items, key=sort_key, reverse=True)

    index_items: list[dict] = []
    for it in items_sorted:
        slug = it["slug"]
        post_dir = posts_root / slug
        body_path = post_dir / "body.html"
        media_map_path = post_dir / "media_map.json"

        post = it["post"]
        title = post.get("title") or slug
        date = iso_to_date(it.get("post_date"))
        subtitle = post.get("description") or ""
        source_url = post.get("canonical_url") or ""
        if not isinstance(source_url, str) or not source_url:
            source_url = f"https://yinwang1.substack.com/p/{slug}"
        paid = post.get("audience") not in (None, "", "everyone")

        body_html = body_path.read_text(encoding="utf-8")
        media_map = read_json(media_map_path) if media_map_path.exists() else {}

        # copy media
        src_media_dir = post_dir / "media"
        out_media_dir = site_dir / "assets" / "posts" / slug
        ensure_dir(out_media_dir)
        if src_media_dir.exists():
            for p in src_media_dir.iterdir():
                if p.is_file():
                    shutil.copy2(p, out_media_dir / p.name)

        rewritten = rewrite_images(body_html, media_map, rel_prefix=f"../../assets/posts/{slug}/")
        post_html = render_page(
            title=title,
            subtitle=date,
            content_html=rewritten,
            css_href="../../assets/style.css",
            home_href="../../",
            source_url=source_url,
            paid=bool(paid),
        )

        out_post_dir = site_dir / "posts" / slug
        ensure_dir(out_post_dir)
        (out_post_dir / "index.html").write_text(post_html, encoding="utf-8")

        index_items.append({"slug": slug, "title": title, "date": date, "paid": bool(paid)})

    (site_dir / "index.html").write_text(render_index(index_items), encoding="utf-8")


if __name__ == "__main__":
    main()
