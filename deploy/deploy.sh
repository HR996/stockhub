#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/stockhub}"
UV="${UV:-/home/ubuntu/.local/bin/uv}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/log}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/deploy-$(date '+%Y%m%d-%H%M%S').log}"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
    printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

on_error() {
    local exit_code=$?
    log "部署失败：第 ${BASH_LINENO[0]} 行，命令：${BASH_COMMAND}，退出码：${exit_code}"
    log "完整日志：$LOG_FILE"
    exit "$exit_code"
}

trap on_error ERR

log "开始部署 istock"
log "项目目录：$PROJECT_DIR"
log "日志文件：$LOG_FILE"

cd "$PROJECT_DIR"

log "同步 Git 代码"
git status --short
git pull --ff-only
log "当前提交：$(git rev-parse --short HEAD) $(git log -1 --pretty=%s)"

log "安装后端依赖"
cd "$PROJECT_DIR/backend"
log "uv 版本：$("$UV" --version)"
"$UV" sync --frozen --no-dev

log "执行数据库迁移"
"$UV" run alembic upgrade head
"$UV" run alembic current

log "安装前端依赖"
cd "$PROJECT_DIR/frontend"
log "Node 版本：$(node --version)，npm 版本：$(npm --version)"
npm ci

log "执行前端类型检查"
npm run typecheck

log "构建前端生产产物"
npm run build

log "发布前端静态文件"
sudo install -d -o root -g www-data -m 0755 /var/www/istock
sudo rsync -a --delete "$PROJECT_DIR/frontend/dist/" /var/www/istock/
sudo chown -R root:www-data /var/www/istock
sudo find /var/www/istock -type d -exec chmod 0755 {} +
sudo find /var/www/istock -type f -exec chmod 0644 {} +

log "安装 systemd 和 nginx 配置"
sudo install -m 0644 "$PROJECT_DIR/deploy/istock.service" /etc/systemd/system/istock.service
# Certbot's live files are symlinks into /etc/letsencrypt/archive, which is
# commonly inaccessible to the deployment user.  Check as root so a valid
# certificate is not mistaken for a missing one.
if sudo test -f /etc/letsencrypt/live/julyquant.site/fullchain.pem; then
    sudo install -m 0644 "$PROJECT_DIR/deploy/nginx-istock.conf" /etc/nginx/sites-available/istock
else
    log "未发现 julyquant.site 证书，使用 HTTP bootstrap nginx 配置"
    sudo install -m 0644 "$PROJECT_DIR/deploy/nginx-istock-http-bootstrap.conf" /etc/nginx/sites-available/istock
fi
sudo ln -sfn /etc/nginx/sites-available/istock /etc/nginx/sites-enabled/istock
sudo rm -f /etc/nginx/sites-enabled/default

log "校验配置并重启服务"
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl enable --now postgresql istock nginx
sudo systemctl restart istock nginx

log "检查服务状态"
sudo systemctl --no-pager --full status istock nginx postgresql || true

log "等待后端启动并验证健康检查"
health_ok=false
for attempt in {1..30}; do
    if curl --fail --silent --show-error http://127.0.0.1/api/health; then
        echo
        health_ok=true
        break
    fi

    log "健康检查尚未通过（${attempt}/30），2 秒后重试"
    sleep 2
done

if [[ "$health_ok" != true ]]; then
    log "健康检查超时，输出 istock 最近日志"
    sudo journalctl -u istock -n 100 --no-pager
    exit 1
fi

log "部署成功"
log "完整日志：$LOG_FILE"
