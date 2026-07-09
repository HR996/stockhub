#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/stockhub}"
UV="${UV:-/home/ubuntu/.local/bin/uv}"

cd "$PROJECT_DIR"

git pull --ff-only

cd "$PROJECT_DIR/backend"
"$UV" sync --frozen --no-dev
"$UV" run alembic upgrade head

cd "$PROJECT_DIR/frontend"
npm ci
npm run typecheck
npm run build

sudo install -m 0644 "$PROJECT_DIR/deploy/istock.service" /etc/systemd/system/istock.service
sudo install -m 0644 "$PROJECT_DIR/deploy/nginx-istock.conf" /etc/nginx/sites-available/istock
sudo ln -sfn /etc/nginx/sites-available/istock /etc/nginx/sites-enabled/istock
sudo rm -f /etc/nginx/sites-enabled/default

sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl enable --now postgresql istock nginx
sudo systemctl restart istock nginx

curl --fail --silent --show-error http://127.0.0.1/api/health
echo
