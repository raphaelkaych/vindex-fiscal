#!/usr/bin/env bash
# Biblioteca privada; não substitui o SQLite do sistema operacional.
set -euo pipefail
umask 077
sqlite_prefix="${VINDEX_SQLITE_PREFIX:-/opt/vindex/sqlite}"
case "$sqlite_prefix" in /*) ;; *) echo 'Use um prefixo absoluto.' >&2; exit 1;; esac
build_dir="$(mktemp -d /tmp/vindex-sqlite.XXXXXXXX)"
trap 'case "$build_dir" in /tmp/vindex-sqlite.*) rm -rf -- "$build_dir";; esac' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  https://www.sqlite.org/2026/sqlite-autoconf-3540100.tar.gz -o "$build_dir/source.tar.gz"
python3 - "$build_dir/source.tar.gz" <<'PY'
import hashlib,sys
from pathlib import Path
expected='b6ced585c750916b1052667239a12c25a7ff34e7f06e1e6e01ecb0427657d9c4'
if hashlib.sha3_256(Path(sys.argv[1]).read_bytes()).hexdigest()!=expected:raise SystemExit('Arquivo SQLite difere do SHA3 oficial; instalação interrompida.')
PY
tar -xzf "$build_dir/source.tar.gz" -C "$build_dir"
cd "$build_dir/sqlite-autoconf-3540100"
./configure --prefix="$sqlite_prefix" --disable-static
make -j2
make install
LD_LIBRARY_PATH="$sqlite_prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" python3 -c "import sqlite3; print('SQLite privado:',sqlite3.sqlite_version); assert sqlite3.sqlite_version_info >= (3,51,3)"
