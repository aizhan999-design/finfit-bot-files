#!/bin/bash
# Установка FinFit бота на сервере Ubuntu
# Запуск: bash install_on_server.sh

set -euo pipefail

APP_DIR="/opt/finbot"
cd "$APP_DIR"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cat > /etc/systemd/system/finbot.service << 'EOF'
[Unit]
Description=FinFit Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/finbot
ExecStart=/opt/finbot/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/sites-available/finbot << 'EOF'
server {
    listen 80;
    server_name _;

    location /robokassa/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/finbot /etc/nginx/sites-enabled/finbot
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

systemctl daemon-reload
systemctl enable finbot
systemctl restart finbot

echo ""
echo "=== Статус ==="
systemctl is-active finbot
journalctl -u finbot -n 10 --no-pager
echo ""
echo "ResultURL для Robokassa: http://147.45.150.25/robokassa/result"
