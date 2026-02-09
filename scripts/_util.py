from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://yinwang1.substack.com"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_filename(name: str, max_len: int = 80) -> str:
    name = name.strip().replace(" ", "-")
    name = re.sub(r"[^0-9A-Za-z\-_.]+", "_", name)
    if len(name) > max_len:
        root, dot, ext = name.rpartition(".")
        if dot:
            root = root[: max_len - (len(ext) + 1)]
            return f"{root}.{ext}"
        return name[:max_len]
    return name


def guess_ext_from_url(url: str) -> str:
    # keep it conservative; prefer jpg/png/webp/gif
    lowered = url.lower().split("?")[0].split("#")[0]
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if lowered.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ""


def ext_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(ct, "")


@dataclass(frozen=True)
class HttpConfig:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0 Safari/537.36"
    )
    cookie: str | None = None
    timeout_s: int = 30
    sleep_s: float = 0.4


def make_session(cfg: HttpConfig) -> requests.Session:
    sess = requests.Session()
    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    if cfg.cookie:
        headers["Cookie"] = cfg.cookie
    sess.headers.update(headers)
    return sess


def http_get_json(sess: requests.Session, url: str, timeout_s: int) -> Any:
    resp = sess.get(url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.json()


def http_get_bytes(sess: requests.Session, url: str, timeout_s: int) -> tuple[bytes, str | None]:
    resp = sess.get(url, timeout=timeout_s, stream=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type")
    return resp.content, content_type


def polite_sleep(cfg: HttpConfig) -> None:
    if cfg.sleep_s > 0:
        time.sleep(cfg.sleep_s)


def env_http_config() -> HttpConfig:
    base_url = os.environ.get("SUBSTACK_BASE_URL", DEFAULT_BASE_URL).strip()
    cookie = os.environ.get("SUBSTACK_COOKIE")
    sleep_s = float(os.environ.get("SUBSTACK_SLEEP_S", "0.4"))
    timeout_s = int(os.environ.get("SUBSTACK_TIMEOUT_S", "30"))
    return HttpConfig(base_url=base_url, cookie=cookie, sleep_s=sleep_s, timeout_s=timeout_s)
