from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch  # noqa: E402
from _util import HttpConfig  # noqa: E402


class FetchMainTests(unittest.TestCase):
    def test_missing_post_is_skipped_and_later_posts_are_saved(self) -> None:
        not_found_response = requests.Response()
        not_found_response.status_code = 404
        not_found = requests.HTTPError(response=not_found_response)

        def get_post(_session, url: str, timeout_s: int):
            del timeout_s
            if url.endswith("/missing"):
                raise not_found
            return {"slug": "available", "title": "Available", "body_html": "<p>ok</p>"}

        archive = [
            {"slug": "missing", "title": "Missing"},
            {"slug": "available", "title": "Available"},
        ]

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            sys, "argv", ["fetch.py", "--raw-dir", tmp, "--skip-media"]
        ), patch.object(
            fetch, "env_http_config", return_value=HttpConfig(base_url="https://example.test")
        ), patch.object(
            fetch, "make_session", return_value=object()
        ), patch.object(
            fetch, "fetch_archive", return_value=archive
        ), patch.object(
            fetch, "http_get_json", side_effect=get_post
        ), patch.object(
            fetch, "polite_sleep"
        ):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                fetch.main()

            raw_dir = Path(tmp)
            self.assertFalse((raw_dir / "posts" / "missing" / "post.json").exists())
            self.assertEqual(
                (raw_dir / "posts" / "available" / "body.html").read_text(encoding="utf-8"),
                "<p>ok</p>",
            )
            self.assertIn("HTTP 404", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
