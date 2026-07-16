# tcloud 生产部署手册

本文记录将本地 istock 数据库和应用部署到 Ubuntu 服务器的完整流程。
当前生产目录为 `/home/ubuntu/stockhub`，前端构建产物发布到
`/var/www/istock`。nginx 对外监听 80/443 端口，FastAPI 仅监听
`127.0.0.1:8000`，PostgreSQL 仅使用本机连接。
生产域名为 `julyquant.site`。

## 1. 服务器依赖

```bash
ssh tcloud
sudo apt-get update
sudo apt-get install -y \
  postgresql postgresql-client nginx nodejs npm curl ca-certificates \
  certbot python3-certbot-nginx

curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-installer.sh
sh /tmp/uv-installer.sh
rm /tmp/uv-installer.sh
```

确认版本：

```bash
psql --version
nginx -v
node --version
npm --version
~/.local/bin/uv --version
```

## 2. 创建生产数据库

数据库仅监听服务器本机，不要向公网开放 5432。

```bash
sudo -u postgres psql -c "CREATE ROLE istock LOGIN PASSWORD 'istock';"
sudo -u postgres createdb -O istock istock
sudo systemctl enable --now postgresql
```

生产连接串：

```text
postgresql+psycopg://istock:istock@localhost:5432/istock
```

正式环境可更换为随机强密码，并同步修改 `backend/.env`。

## 3. 从本机迁移数据库

先在本机创建 PostgreSQL custom-format 备份：

```bash
cd /Users/rayee/Project/stockhub
set -a
source backend/.env
set +a
pg_dump \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-acl \
  --file=/tmp/istock.dump \
  "${DATABASE_URL/postgresql+psycopg/postgresql}"
shasum -a 256 /tmp/istock.dump
scp /tmp/istock.dump tcloud:/home/ubuntu/istock.dump
```

在服务器校验并恢复。目标库已有数据时，先备份再使用 `--clean`：

```bash
ssh tcloud
sha256sum /home/ubuntu/istock.dump

sudo -u postgres pg_dump \
  --format=custom \
  --file=/home/ubuntu/istock-before-restore.dump \
  istock

pg_restore \
  --exit-on-error \
  --no-owner \
  --no-acl \
  --dbname=postgresql://istock:istock@localhost:5432/istock \
  /home/ubuntu/istock.dump

psql postgresql://istock:istock@localhost:5432/istock \
  -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

确认恢复无误后删除传输文件：

```bash
rm /home/ubuntu/istock.dump
```

## 4. 同步代码和生产环境变量

正常发布使用 Git：

```bash
ssh tcloud
cd /home/ubuntu/stockhub
git pull --ff-only
```

首次部署时，在服务器创建 `backend/.env`（该文件不能提交到 Git）：

```dotenv
DATABASE_URL=postgresql+psycopg://istock:istock@localhost:5432/istock
PRECONFIGURED_USERS=admin,alice,bob
ADMIN_PASSWORD_HASH=<实际哈希>
TUSHARE_TOKEN=<实际令牌>
SCHEDULER_ENABLED=true
SCHEDULER_HOUR=17
SCHEDULER_MINUTE=0
SCHEDULER_TRIGGERED_BY=scheduler
SCHEDULER_SW_ENABLED=false
SCHEDULER_SW_DAY_OF_WEEK=sat
SCHEDULER_SW_HOUR=2
SCHEDULER_SW_MINUTE=7
```

```bash
chmod 600 /home/ubuntu/stockhub/backend/.env
```

## 5. 域名解析和 HTTPS

腾讯云域名 `julyquant.site` 需要先完成备案和 DNS 解析。当前服务器公网 IP：

```text
124.220.55.215
```

在腾讯云 DNS 解析中添加：

| 主机记录 | 记录类型 | 记录值 |
| --- | --- | --- |
| `@` | `A` | `124.220.55.215` |
| `www` | `A` | `124.220.55.215` |

腾讯云安全组开放 TCP `22`、`80`、`443`，不要开放 `5432` 或 `8000`。

首次启用 HTTPS 的顺序：

```bash
ssh tcloud
cd /home/ubuntu/stockhub
./deploy/deploy.sh

sudo certbot --nginx \
  -d julyquant.site \
  -d www.julyquant.site \
  --redirect

./deploy/deploy.sh
```

第一次执行 `deploy.sh` 时，如果证书还不存在，脚本会安装
`deploy/nginx-istock-http-bootstrap.conf`，用于通过 HTTP 访问和完成
Let's Encrypt 域名验证。证书签发成功后再次执行 `deploy.sh`，脚本会自动切换到
`deploy/nginx-istock.conf`，启用 HTTPS，并把 HTTP 请求 301 跳转到 HTTPS。

验证：

```bash
curl -I http://julyquant.site
curl https://julyquant.site/api/health
sudo certbot renew --dry-run
```

浏览器访问：

```text
https://julyquant.site/
https://julyquant.site/api/docs
```

## 6. 安装、构建和启动

仓库提供了可重复执行的部署脚本：

```bash
cd /home/ubuntu/stockhub
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

脚本会执行：

1. `git pull --ff-only`；
2. `uv sync --frozen --no-dev`；
3. `alembic upgrade head`；
4. `npm ci`、类型检查及 Vite 生产构建；
5. 将前端静态文件发布到 `/var/www/istock`；
6. 安装 systemd/nginx 配置，证书存在时启用 HTTPS，否则使用 HTTP bootstrap 配置；
7. 启动服务并等待健康检查通过。

手工查看状态：

```bash
sudo systemctl status istock nginx postgresql
sudo journalctl -u istock -n 100 --no-pager
curl http://127.0.0.1/api/health
curl https://julyquant.site/api/health
```

浏览器访问：

```text
https://julyquant.site/
https://julyquant.site/api/docs
```

## 7. 日常发布与回滚

发布前在本地完成测试并推送 Git 提交，然后在服务器执行：

```bash
ssh tcloud 'cd /home/ubuntu/stockhub && ./deploy/deploy.sh'
```

回滚到已知稳定提交：

```bash
ssh tcloud
cd /home/ubuntu/stockhub
git log --oneline -n 10
git switch --detach <稳定提交>

cd backend
~/.local/bin/uv sync --frozen --no-dev
cd ../frontend
npm ci
npm run build
sudo systemctl restart istock nginx
```

Alembic 数据库迁移不应盲目降级。涉及 schema 回滚时，应先恢复发布前数据库备份。

## 8. 安全和运维

- 腾讯云安全组只需开放 TCP 22、80、443。
- 不要开放 PostgreSQL 5432 或 FastAPI 8000。
- `backend/.env` 权限保持为 `600`，不得提交到 Git。
- HTTPS 证书由 Certbot/Let's Encrypt 维护，systemd timer 会自动续期；定期执行 `sudo certbot renew --dry-run` 验证续期链路。
- 建议每日执行 `pg_dump --format=custom` 并将备份保存到异机或对象存储。
- 定期检查 `df -h`、`systemctl status istock` 和 `journalctl -u istock`。
