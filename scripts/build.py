from __future__ import annotations

import argparse
import html
import shutil
from datetime import datetime, timezone
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


def render_page(title: str, subtitle: str, content_html: str, *, css_href: str, home_href: str) -> str:
    safe_title = html.escape(title)
    safe_sub = html.escape(subtitle) if subtitle else ""
    sub_block = f"<p class=\"subtitle\">{safe_sub}</p>" if safe_sub else ""
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
        {sub_block}
        <article class=\"post\">{content_html}</article>
      </main>
      <footer class=\"footer\">
        <p>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.</p>
      </footer>
    </div>
  </body>
</html>"""


def render_index(items: list[dict]) -> str:
    li = []
    for it in items:
        title = html.escape(it["title"])
        date = html.escape(it["date"])
        slug = it["slug"]
        li.append(f"<li><a href=\"/posts/{slug}/\">{title}</a><span class=\"date\">{date}</span></li>")
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
    </div>
  </body>
</html>"""


def write_style(site_dir: Path) -> None:
    css = """
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', 'Microsoft Yahei', sans-serif; line-height: 1.6; }
.container { max-width: 860px; margin: 0 auto; padding: 24px; }
.header { margin-bottom: 18px; }
.home { text-decoration: none; color: inherit; }
.subtitle { color: #666; margin-top: -8px; }
.index { list-style: none; padding-left: 0; }
.index li { display: flex; gap: 12px; align-items: baseline; padding: 6px 0; }
.index a { text-decoration: none; }
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

    archive = read_json(raw_dir / "archive.json")
    # sort by post_date desc
    def key(x):
        return x.get("post_date") or ""

    archive_sorted = sorted([a for a in archive if a.get("slug")], key=key, reverse=True)

    index_items: list[dict] = []
    for a in archive_sorted:
        slug = a["slug"]
        post_dir = raw_dir / "posts" / slug
        post_json_path = post_dir / "post.json"
        body_path = post_dir / "body.html"
        media_map_path = post_dir / "media_map.json"
        if not post_json_path.exists() or not body_path.exists():
            continue

        post = read_json(post_json_path)
        title = post.get("title") or slug
        date = iso_to_date(post.get("post_date") or a.get("post_date"))
        subtitle = post.get("description") or ""

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
        )

        out_post_dir = site_dir / "posts" / slug
        ensure_dir(out_post_dir)
        (out_post_dir / "index.html").write_text(post_html, encoding="utf-8")

        index_items.append({"slug": slug, "title": title, "date": date})

    (site_dir / "index.html").write_text(render_index(index_items), encoding="utf-8")


if __name__ == "__main__":
    main()
