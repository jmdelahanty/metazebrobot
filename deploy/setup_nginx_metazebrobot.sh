#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="metazebrobot"
UPSTREAM_URL="${UPSTREAM_URL:-http://127.0.0.1:8000}"
ENABLE_WRITE_AUTH="${ENABLE_WRITE_AUTH:-1}"
WRITE_AUTH_USER="${WRITE_AUTH_USER:-delahantyj}"
WRITE_AUTH_FILE="${WRITE_AUTH_FILE:-/etc/nginx/.htpasswd-metazebrobot}"
SITE_AVAILABLE="/etc/nginx/sites-available/${SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
DEFAULT_ENABLED="/etc/nginx/sites-enabled/default"

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed. Install it first, for example: sudo apt-get install nginx" >&2
  exit 1
fi

echo "Configuring nginx site ${SITE_NAME} -> ${UPSTREAM_URL}"

AUTH_LIMIT_EXCEPT=""
if [[ "$ENABLE_WRITE_AUTH" != "0" && "$ENABLE_WRITE_AUTH" != "false" ]]; then
  if [[ ! -f "$WRITE_AUTH_FILE" ]]; then
    if ! command -v openssl >/dev/null 2>&1; then
      echo "openssl is required to create ${WRITE_AUTH_FILE}" >&2
      exit 1
    fi
    read -r -s -p "New write password for ${WRITE_AUTH_USER}: " WRITE_AUTH_PASSWORD
    echo
    read -r -s -p "Confirm write password: " WRITE_AUTH_PASSWORD_CONFIRM
    echo
    if [[ "$WRITE_AUTH_PASSWORD" != "$WRITE_AUTH_PASSWORD_CONFIRM" ]]; then
      echo "Passwords did not match." >&2
      exit 1
    fi
    if [[ -z "$WRITE_AUTH_PASSWORD" ]]; then
      echo "Password cannot be empty." >&2
      exit 1
    fi
    WRITE_AUTH_HASH="$(printf '%s' "$WRITE_AUTH_PASSWORD" | openssl passwd -apr1 -stdin)"
    unset WRITE_AUTH_PASSWORD WRITE_AUTH_PASSWORD_CONFIRM
    printf '%s:%s\n' "$WRITE_AUTH_USER" "$WRITE_AUTH_HASH" \
      | sudo tee "$WRITE_AUTH_FILE" >/dev/null
    sudo chmod 640 "$WRITE_AUTH_FILE"
    sudo chown root:www-data "$WRITE_AUTH_FILE"
    echo "Created ${WRITE_AUTH_FILE} for write auth user ${WRITE_AUTH_USER}."
  else
    echo "Using existing write auth file ${WRITE_AUTH_FILE}."
  fi

  AUTH_LIMIT_EXCEPT="
        limit_except GET OPTIONS {
            auth_basic \"MetaZebrobot write access\";
            auth_basic_user_file ${WRITE_AUTH_FILE};
        }"
  echo "Write auth enabled: GET/HEAD/OPTIONS are public; mutating requests require Basic Auth."
else
  echo "Write auth disabled."
fi

sudo tee "$SITE_AVAILABLE" >/dev/null <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    access_log /var/log/nginx/metazebrobot.access.log;
    error_log /var/log/nginx/metazebrobot.error.log;

    location / {
${AUTH_LIMIT_EXCEPT}
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
