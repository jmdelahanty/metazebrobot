#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${CONFIG_FILE:-$REPO_ROOT/config.json}"
OUTPUT_FILE="${OUTPUT_FILE:-$REPO_ROOT/docs/schema.sql}"

if [[ -n "${DB_PATH:-}" ]]; then
  db_path="$DB_PATH"
else
  if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config file not found: $CONFIG_FILE" >&2
    exit 1
  fi
  export CONFIG_FILE
  db_path="$(python3 - <<'PY'
import json
import os
import sys

config_file = os.environ.get("CONFIG_FILE")
with open(config_file, "r", encoding="utf-8") as f:
    cfg = json.load(f)
db_path = cfg.get("database_path")
if not db_path:
    sys.stderr.write("database_path missing in config.json\n")
    sys.exit(2)
print(db_path)
PY
)"
fi

if [[ ! -f "$db_path" ]]; then
  echo "Database not found: $db_path" >&2
  exit 3
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$db_path" ".schema" > "$OUTPUT_FILE"
else
  export DB_PATH="$db_path"
  python3 - <<'PY' > "$OUTPUT_FILE"
import os
import sqlite3

db_path = os.environ["DB_PATH"]
conn = sqlite3.connect(db_path)
try:
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
        "ORDER BY type='table' DESC, name"
    )
    for (sql,) in cur.fetchall():
        print(f"{sql};")
finally:
    conn.close()
PY
fi

echo "Wrote schema to $OUTPUT_FILE"
