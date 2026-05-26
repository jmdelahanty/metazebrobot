#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8000}"
DB_PATH="${DB_PATH:-/nvme1/zebrobot.db}"
HOST="${HOST:-127.0.0.1}"
LOG_FILE="${LOG_FILE:-./.metazebrobot-server.log}"
PID_FILE="${PID_FILE:-./.metazebrobot-server.pid}"
SERVICE_NAME="${SERVICE_NAME:-metazebrobot-api}"
USE_SYSTEMD="${USE_SYSTEMD:-auto}"

systemd_unit_available() {
  command -v systemctl >/dev/null 2>&1 && systemctl cat "$SERVICE_NAME" >/dev/null 2>&1
}

run_systemctl_restart() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl restart "$SERVICE_NAME"
  else
    sudo systemctl restart "$SERVICE_NAME"
  fi
}

if [[ "$USE_SYSTEMD" != "0" && "$USE_SYSTEMD" != "false" ]] && systemd_unit_available; then
  echo "Restarting systemd service ${SERVICE_NAME}"
  run_systemctl_restart
  systemctl is-active "$SERVICE_NAME"
  if command -v curl >/dev/null 2>&1; then
    curl -sS -o /tmp/metazebrobot-restart-health.txt -w "HTTP %{http_code}\n" \
      "http://127.0.0.1:${PORT}/health?check_db=true" || true
    cat /tmp/metazebrobot-restart-health.txt 2>/dev/null || true
    echo
  fi
  exit 0
fi

echo "Starting manual server process. Set USE_SYSTEMD=auto to prefer ${SERVICE_NAME} when available."

find_listening_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$PORT" 2>/dev/null || true
  else
    pgrep -f "metazebrobot[.]api_server.*--port[ =]$PORT" 2>/dev/null || true
  fi
}

stop_pid() {
  local pid="$1"

  if [[ -z "$pid" || "$pid" == "$$" ]]; then
    return 0
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  echo "Stopping existing server process $pid"
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done

  echo "Process $pid did not stop after SIGTERM; sending SIGKILL"
  kill -KILL "$pid" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
  stop_pid "$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
fi

mapfile -t PORT_PIDS < <(find_listening_pids | tr ' ' '\n' | awk 'NF && !seen[$0]++')
for pid in "${PORT_PIDS[@]}"; do
  stop_pid "$pid"
done

if command -v pixi >/dev/null 2>&1; then
  CMD=(pixi run python -m metazebrobot.api_server --db-path "$DB_PATH" --port "$PORT")
else
  CMD=(python3 -m metazebrobot.api_server --db-path "$DB_PATH" --port "$PORT")
fi

if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
  CMD+=(--host "$HOST")
fi

CMD+=("$@")

mkdir -p "$(dirname "$LOG_FILE")"
echo "Starting server on http://$HOST:$PORT/"
echo "Log: $LOG_FILE"
nohup "${CMD[@]}" >"$LOG_FILE" 2>&1 &
SERVER_PID="$!"
echo "$SERVER_PID" > "$PID_FILE"

echo "Started server process $SERVER_PID"
echo "Command: ${CMD[*]}"
