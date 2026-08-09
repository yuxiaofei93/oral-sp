# 阿里云 Debian 13 原生内测部署

本文档适用于当前内测环境：

- 阿里云 ECS，Debian GNU/Linux 13 (trixie)。
- 学生端：`https://wenzhen.wishine.top`。
- 教师端：`https://manage.wishine.top`。
- 1 核 1 GB，不使用 Docker、PostgreSQL 或 Caddy。
- Nginx 提供双域名、React 静态文件、HTTPS 和反向代理。
- Gunicorn 使用 1 个 worker 和 4 个线程运行 Django API，监听 `127.0.0.1:8010`，避免与同机现有的 FamilyLedger `127.0.0.1:8000` 冲突。
- 项目位于 `/home/nick/oral-sp`，SQLite 保存在 `/home/nick/oral-sp/var/production.sqlite3`，不迁移本地测试数据。

Gunicorn 不能单独提供这套系统：它只运行 Django WSGI API，不负责 React 静态文件、两个域名或 HTTPS。Nginx 是很轻量的必要入口层。

## 1. DNS 和阿里云安全组

在阿里云 DNS 中添加两条 A 记录，记录值都是 ECS 的公网 IPv4：

| 主机记录 | 类型 | 记录值 |
| --- | --- | --- |
| `wenzhen` | A | ECS 公网 IPv4 |
| `manage` | A | ECS 公网 IPv4 |

如果存在指向其他服务器的 AAAA 记录，先删除或改正。安全组入方向只需要：

- TCP `80`：来源 `0.0.0.0/0`。
- TCP `443`：来源 `0.0.0.0/0`。
- TCP `22`：仅允许管理员的固定公网 IP。

不要对公网开放 `8000`、`8010`、`5173`、`5174` 或 `5432`。在阿里云备案控制台确认已备案的 `wishine.top` 已经接入当前 ECS。

DNS 生效后检查：

```bash
dig +short wenzhen.wishine.top A
dig +short manage.wishine.top A
```

两条命令都应返回当前 ECS 公网 IPv4。

## 2. 准备 swap

前端首次构建时的内存峰值高于日常运行，1 GB 主机建议配置 2 GB swap。先检查：

```bash
free -h
swapon --show
```

如果已经有 1–2 GB swap，跳过创建步骤。完全没有 swap 时，以下命令只执行一次：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

再次执行 `swapon --show` 确认。

## 3. 安装系统软件

Debian 13 自带的 Node.js 20.19 满足当前 Vite 要求。Nginx、Certbot 和 SQLite 直接使用 Debian 正式软件包：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm nginx certbot sqlite3 dnsutils openssl
python3 --version
node --version
npm --version
nginx -v
```

服务器全局已经安装 Gunicorn 也没有问题，但项目仍会在自己的 `.venv` 里安装锁定版本，避免系统 Gunicorn 与项目 Python 依赖不一致。

## 4. 克隆私有仓库

服务器能通过 SSH 访问私有 GitHub 仓库时：

```bash
cd /home/nick
git clone git@github.com:yuxiaofei93/oral-sp.git oral-sp
cd /home/nick/oral-sp
```

如果提示无权限，在 ECS 生成一对专用 SSH 密钥，将公钥加入 GitHub 仓库的只读 Deploy key。不要把 SSH 私钥、GitHub 密码或令牌放入仓库。

## 5. 安装项目依赖

```bash
cd /home/nick/oral-sp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c apps/api/constraints.txt ./apps/api
.venv/bin/gunicorn --version
```

这会在项目虚拟环境中安装 Django、Gunicorn 及后端依赖。

## 6. 填写生产环境变量

```bash
cd /home/nick/oral-sp
cp deploy/production.env.example .env.production
openssl rand -hex 48
nano .env.production
```

把随机值填到 `DJANGO_SECRET_KEY`，再填写：

- `LLM_API_KEY`：DeepSeek API Key。
- `EMAIL_HOST`、`EMAIL_PORT`、`EMAIL_HOST_USER`、`EMAIL_HOST_PASSWORD`。
- `DEFAULT_FROM_EMAIL`：SMTP 服务允许的发件地址。

模板已经填好双域名、SQLite 地址和 DeepSeek 模型。如果 SMTP 使用 STARTTLS 587，改为：

```dotenv
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

TLS 和 SSL 不能同时为 `true`。阿里云对 TCP 25 有限制，不建议使用 25。密码含 `$`、`#`、空格或其他 shell 特殊字符时，用单引号包住整个值。

不要把本地 `.env` 直接复制上去，也不要把 `.env.production` 提交到 Git。设置文件权限：

```bash
sudo chmod 711 /home/nick
sudo chown root:www-data /home/nick/oral-sp/.env.production
sudo chmod 640 /home/nick/oral-sp/.env.production
sudo install -d -o www-data -g www-data -m 750 /home/nick/oral-sp/var
sudo install -d -o www-data -g www-data -m 750 /home/nick/oral-sp/var/private-media
```

## 7. 初始化 SQLite

```bash
cd /home/nick/oral-sp
sudo -u www-data ./deploy/manage-production.sh check --deploy
sudo -u www-data ./deploy/manage-production.sh migrate
sudo -u www-data ./deploy/manage-production.sh createsuperuser
```

`check --deploy` 在内测期间可能提示尚未启用 HSTS preload 或全子域名 HSTS；这是当前有意保留的策略，不是启动错误。管理员可以在教师域名直接登录。

SQLite 配置使用 20 秒锁等待和 `IMMEDIATE` 事务，Gunicorn 只有一个进程，避免在低配机器上放大写入竞争。如果内测日志出现 `database is locked`，说明并发写入已经超过 SQLite 的适用范围，应迁移 PostgreSQL，而不是继续增加 Gunicorn worker。

## 8. 构建两个前端

```bash
cd /home/nick/oral-sp
./deploy/build-frontends.sh
```

产物分别位于：

- `apps/web/dist/student/`
- `apps/web/dist/teacher/`

构建后确认 Nginx 用户可以读取：

```bash
sudo -u www-data test -r /home/nick/oral-sp/apps/web/dist/student/index.html
sudo -u www-data test -r /home/nick/oral-sp/apps/web/dist/teacher/index.html
```

## 9. 启动 Gunicorn systemd 服务

```bash
cd /home/nick/oral-sp
sudo install -m 644 deploy/oral-sp-api.service /etc/systemd/system/oral-sp-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now oral-sp-api
sudo systemctl status oral-sp-api --no-pager
```

本机检查 API：

```bash
curl --fail --silent --show-error \
  -H 'Host: wenzhen.wishine.top' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8010/api/health/ready/
```

预期返回 `status: ok` 和 `database: ready`。Gunicorn 只监听 `127.0.0.1:8010`，公网不能直接访问。

## 10. 安装 Nginx 初始 HTTP 配置

```bash
cd /home/nick/oral-sp
sudo install -d -m 755 /var/www/certbot
sudo install -m 644 deploy/nginx/oral-sp-http.conf /etc/nginx/sites-available/oral-sp
sudo ln -s /etc/nginx/sites-available/oral-sp /etc/nginx/sites-enabled/oral-sp
```

如果 `/etc/nginx/sites-enabled/default` 存在，只删除这个默认站点的符号链接：

```bash
sudo unlink /etc/nginx/sites-enabled/default
```

然后：

```bash
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
curl --head http://wenzhen.wishine.top/
curl --head http://manage.wishine.top/
```

## 11. 安装 HTTPS 证书

Nginx 从下列固定路径读取学生端和教师端的独立证书：

```bash
sudo install -d -o root -g root -m 700 /etc/nginx/ssl/oral-sp
```

### 方式 A：Let's Encrypt

把命令中的联系邮箱替换成你的证书通知邮箱：

```bash
sudo certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --cert-name oral-sp \
  --domain wenzhen.wishine.top \
  --domain manage.wishine.top \
  --email replace-with-your-email@example.com \
  --agree-tos \
  --no-eff-email
```

证书成功后，将两个域名的标准路径指向同一张多域名证书：

```bash
cd /home/nick/oral-sp
sudo ln -sfn /etc/letsencrypt/live/oral-sp/fullchain.pem /etc/nginx/ssl/oral-sp/wenzhen.pem
sudo ln -sfn /etc/letsencrypt/live/oral-sp/privkey.pem /etc/nginx/ssl/oral-sp/wenzhen.key
sudo ln -sfn /etc/letsencrypt/live/oral-sp/fullchain.pem /etc/nginx/ssl/oral-sp/manage.pem
sudo ln -sfn /etc/letsencrypt/live/oral-sp/privkey.pem /etc/nginx/ssl/oral-sp/manage.key
sudo install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
sudo install -m 755 deploy/certbot-reload-nginx.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
sudo certbot renew --dry-run
```

### 方式 B：阿里云个人测试证书

分别为两个域名下载 Nginx 格式的证书，上传到 `/home/nick/certs-upload`，再安装到固定路径：

```bash
sudo install -m 644 /home/nick/certs-upload/wenzhen.wishine.top.pem /etc/nginx/ssl/oral-sp/wenzhen.pem
sudo install -m 600 /home/nick/certs-upload/wenzhen.wishine.top.key /etc/nginx/ssl/oral-sp/wenzhen.key
sudo install -m 644 /home/nick/certs-upload/manage.wishine.top.pem /etc/nginx/ssl/oral-sp/manage.pem
sudo install -m 600 /home/nick/certs-upload/manage.wishine.top.key /etc/nginx/ssl/oral-sp/manage.key
```

个人测试证书需要在到期前重新申请并重复上述安装操作。

### 启用 HTTPS

证书安装后切换到仓库内的正式 HTTPS 配置：

```bash
cd /home/nick/oral-sp
sudo install -m 644 deploy/nginx/oral-sp.conf /etc/nginx/sites-available/oral-sp
sudo nginx -t
sudo systemctl reload nginx
```

对外检查：

```bash
curl --fail --silent --show-error https://wenzhen.wishine.top/api/health/ready/
curl --fail --silent --show-error https://manage.wishine.top/api/health/ready/
```

浏览器分别打开：

- `https://wenzhen.wishine.top`
- `https://manage.wishine.top`

## 12. 首次内测验收

1. 管理员登录教师端，创建一个班级。
2. 学生端用真实邮箱获取验证码并注册，确认 SMTP 正常。
3. 创建并发布一个最小病例，发布一个测试任务。
4. 学生完成问诊、病例自动保存和最终交卷，确认 DeepSeek 回答正常。
5. 教师查看答卷、辅助评分并发布反馈。
6. 先用 3–5 个并发学生测试，再扩大人数。

检查资源和日志：

```bash
free -h
df -h
systemctl status oral-sp-api nginx --no-pager
sudo journalctl -u oral-sp-api -n 200 --no-pager
```

## 13. SQLite 备份

备份脚本使用 Python 内置的 SQLite 在线备份 API，无需停止 Gunicorn：

```bash
cd /home/nick/oral-sp
sudo ./deploy/backup.sh
```

备份位于 `/home/nick/oral-sp/backups/`，脚本会对备份执行完整性检查，不会自动删除历史文件。建议每日备份并定期复制到 ECS 以外。

每日 03:15 备份：

```bash
sudo crontab -e
```

添加：

```cron
15 3 * * * /home/nick/oral-sp/deploy/backup.sh >> /var/log/oral-sp-backup.log 2>&1
```

恢复 SQLite 会覆盖当前数据。必须先备份当前文件、停止 `oral-sp-api`、确认备份完整后才能操作，不要把恢复放入自动更新脚本。

## 14. 更新部署

首次获取更新脚本：

```bash
cd /home/nick/oral-sp
git pull --ff-only
```

以后每次代码更新只需运行：

```bash
cd /home/nick/oral-sp
./deploy/update-production.sh
```

脚本会在工作区干净且远程分支可快进时，依次执行 SQLite 备份、Git 更新、后端依赖安装、前端构建、数据库迁移、API 重启和就绪检查。它不会更新或重载 Nginx，也不会修改证书。

如果代码已经手动拉取，或需要重试上次失败的部署，强制重新部署当前版本：

```bash
./deploy/update-production.sh --force
```

不要使用 `sudo ./deploy/update-production.sh`；脚本会在需要备份、迁移和重启服务时自行调用 `sudo`。

systemd 或 Nginx 配置变更不属于该脚本的范围，需要另行安装和重载。

数据库迁移不一定可通过切换 Git 提交自动逆转。回滚前根据该版本的迁移情况决定是否恢复 SQLite 备份。

## 15. 排查命令

```bash
sudo systemctl status oral-sp-api nginx --no-pager
sudo journalctl -u oral-sp-api -n 200 --no-pager
sudo tail -n 200 /var/log/nginx/error.log
sudo nginx -t
sudo certbot certificates
sudo -u www-data /home/nick/oral-sp/deploy/manage-production.sh check
```

API 应用日志是单行 JSON。页面显示服务端错误时会附带问题编号，可直接在 journal 中关联请求和业务异常：

```bash
sudo journalctl -u oral-sp-api --since "24 hours ago" --no-pager -o cat \
  | grep -F '替换为问题编号'
```

完整的日志字段、邮件事件和排查流程见 [生产问题定位手册](./production-troubleshooting.md)。

- `oral-sp-api` 启动失败：优先检查 `.env.production`、SQLite 目录权限和 `journalctl`。
- 网站出现 `502 Bad Gateway`：检查 Gunicorn 是否监听 `127.0.0.1:8010`。
- 证书失败：检查 DNS A 记录、80/443 安全组和错误 AAAA 记录。
- 邮件失败：检查 SMTP 授权码、465/587 端口和 TLS/SSL 组合。
- `database is locked`：记录当时并发人数和操作，准备迁移 PostgreSQL。
- 进程被杀或构建卡住：检查 `free -h`、`swapon --show` 和 `dmesg -T | tail`。

## 官方参考

- [Django 使用 Gunicorn](https://docs.djangoproject.com/zh-hans/5.2/howto/deployment/wsgi/gunicorn/)
- [Django SQLite 注意事项](https://docs.djangoproject.com/zh-hans/5.2/ref/databases/#sqlite-notes)
- [Gunicorn PyPI](https://pypi.org/project/gunicorn/)
- [Debian 13 Nginx](https://packages.debian.org/trixie/nginx)
- [Debian 13 Certbot](https://packages.debian.org/trixie/certbot)
- [阿里云 DNS 解析](https://help.aliyun.com/zh/dns/pubz-add-parsing-record)
- [阿里云 ECS 安全组](https://help.aliyun.com/zh/ecs/user-guide/start-using-security-groups)
