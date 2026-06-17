#!/bin/bash
set -euo pipefail

# Запуск на сервере Timeweb (Ubuntu/Debian):
#   apt update && apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
#   mkdir -p /opt/finbot && cd /opt/finbot
#   # скопируйте файлы проекта и .env
#   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
#   cp finbot.service /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable --now finbot

APP_DIR="/opt/finbot"
DOMAIN="${1:-}"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "Создайте $APP_DIR/.env перед деплоем"
  exit 1
fi

cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp finbot.service /etc/systemd/system/finbot.service
systemctl daemon-reload
systemctl enable finbot
systemctl restart finbot

if [ -n "$DOMAIN" ]; then
  cat > /etc/nginx/sites-available/finbot <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location /robokassa/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/finbot /etc/nginx/sites-enabled/finbot
  nginx -t && systemctl reload nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@${DOMAIN} || true
  echo "ResultURL для Robokassa: https://${DOMAIN}/robokassa/result"
fi

systemctl status finbot --no-pager
