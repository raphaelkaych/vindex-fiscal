#!/usr/bin/env bash
set -euo pipefail
umask 077
export LD_LIBRARY_PATH="${VINDEX_SQLITE_LIB_DIR:-/opt/vindex/sqlite/lib}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$(dirname "$0")/.."
command -v python3 >/dev/null
command -v pm2 >/dev/null || { echo 'Instale PM2 antes de continuar; veja docs/LINUX-PM2.md.' >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-production.txt
.venv/bin/python -m pip check
export DJANGO_SETTINGS_MODULE=config.production
export VINDEX_ENV_FILE="${VINDEX_ENV_FILE:-/etc/vindex/vindex.env}"
.venv/bin/python tools/prepare_release.py
