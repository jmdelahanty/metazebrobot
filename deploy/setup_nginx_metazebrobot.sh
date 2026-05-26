#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="metazebrobot"
UPSTREAM_URL="${UPSTREAM_URL:-http://127.0.0.1:8000}"
SITE_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
DEFAULT_ENABLED="/etc/nginx/sites-enabled/default"

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed. Install it first, for example: sudo apt-get install nginx" >&2
  exit 1
fi

echo "Configuring nginx site ${SITE_NAME} -> ${UPSTREAM_URL}"

sudo tee "$SITE_AVAILABLE" >/dev/null <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    access_log /var/log/nginx/metazebrobot.access.log;
    error_log /var/log/nginx/metazebrobot.error.log;

    location / {
        proxy_pass ${UPSTREAM_URL};
        proxy_http_version 1.1;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo rm -f "$DEFAULT_ENABLED"
sudo ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"
sudo nginx -t
sudo systemctl reload nginx

echo "nginx reloaded."
echo "Local check:"
curl -sS -o /tmp/metazebrobot-nginx-health.txt -w "HTTP %{http_code}\n" \
  "http://127.0.0.1/health?check_db=true" || true
cat /tmp/metazebrobot-nginx-health.txt 2>/dev/null || true
echo
