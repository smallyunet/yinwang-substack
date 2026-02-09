#!/usr/bin/env bash
set -euo pipefail

./.venv/bin/python scripts/fetch.py "$@"
./.venv/bin/python scripts/build.py