# Gitee Go + 阿里云 ACR 内测部署

本文档适用于当前环境：

- Gitee 私有仓库，`main` 分支。
- Gitee Go 在云端测试并构建镜像。
- 阿里云 ACR 个人版，广州地域。
- 阿里云 ECS，Debian 13，x86_64，1 核 1 GB。
- SQLite 保存在宿主机，不迁移本地测试数据。
- 宿主机 Nginx 和 Certbot 负责双域名及 HTTPS。
- ECS 通过 SSH 手动部署，不安装 Gitee Go Agent。

## 1. 部署结构

Gitee Go 构建并推送三个镜像：

| 镜像仓库 | 内容 | ECS 监听地址 |
| --- | --- | --- |
| `oral-sp/oral-sp-api` | Django + Gunicorn | `127.0.0.1:8000` |
| `oral-sp/oral-sp-student` | 学生端静态页面 + Nginx | `127.0.0.1:5173` |
| `oral-sp/oral-sp-teacher` | 教师端静态页面 + Nginx | `127.0.0.1:5174` |

每次流水线使用 `build-${GITEE_PIPELINE_BUILD_NUMBER}` 作为三个镜像的共同版本。服务器只拉取镜像，不执行 Python、Node.js 或 Docker 镜像构建。

## 2. 创建 ACR 仓库

当前 ACR 信息：

```text
公网地址：crpi-iyetp24mk5qki59e.cn-guangzhou.personal.cr.aliyuncs.com
VPC 地址：crpi-iyetp24mk5qki59e-vpc.cn-guangzhou.personal.cr.aliyuncs.com
命名空间：oral-sp
```

在 ACR 控制台的 `oral-sp` 命名空间中创建三个私有仓库：

```text
oral-sp-api
oral-sp-student
oral-sp-teacher
```

Gitee Go 推送镜像时使用公网地址；广州 ECS 拉取镜像时优先使用 VPC 地址。ACR 个人版仅适合当前开发内测，没有 SLA，正式生产前需要重新评估。

## 3. Gitee Go 流水线

当前已经创建“Docker 仓库账号密码”凭证：

```text
凭证名称：oral-sp-gitee-go
凭证 ID：6156e620-74a7-013f-1849-323791aaa193
```

凭证 ID 是安全引用，可以保存在流水线中；ACR 用户名和 Registry 密码只保存在 Gitee 凭证管理中，不写入仓库。

仓库中的 [正式流水线](../.workflow/oral-sp-acr.yml) 会在 `main` 分支收到提交后自动执行：

1. 构建 API 镜像并运行 Ruff 和后端测试。
2. 构建学生端镜像并运行前端测试与生产构建。
3. 构建教师端镜像并运行前端测试与生产构建。
4. 使用同一个 `build-N` 标签推送到三个 ACR 仓库。

任意镜像测试或构建失败时，流水线会失败。部署不属于流水线，避免在 1 GB ECS 上安装常驻 Gitee Go Agent；确认三个镜像均已推送后，再通过 SSH 发布指定的 `build-N` 版本。

## 4. 安装 Docker Engine

在 ECS 上按照 Docker 官方 Debian 软件源安装 Engine 和 Compose 插件：

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx certbot python3 dnsutils openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

1 GB 内存建议配置 2 GB swap，操作方法见 [Debian 原生部署文档](./deployment-aliyun-debian.md#2-准备-swap)。

## 5. 准备服务器目录

```bash
sudo install -d -o "$USER" -g "$USER" /opt/oral-sp
git clone git@gitee.com:Nick2019/oral-sp.git /opt/oral-sp
cd /opt/oral-sp

cp deploy/acr.env.example .env.deploy
cp deploy/container-production.env.example .env.production
openssl rand -hex 48
nano .env.production
```

把随机值填入 `DJANGO_SECRET_KEY`，并填写 DeepSeek 与 SMTP 配置。不要提交 `.env.deploy` 或 `.env.production`。

SQLite 容器使用固定 UID `10001`：

```bash
sudo install -d -o 10001 -g 10001 -m 750 /opt/oral-sp/var
sudo install -d -o 10001 -g 10001 -m 750 /opt/oral-sp/var/private-media
sudo install -d -o root -g root -m 700 /opt/oral-sp/backups
sudo chown root:root /opt/oral-sp/.env.deploy /opt/oral-sp/.env.production
sudo chmod 600 /opt/oral-sp/.env.deploy /opt/oral-sp/.env.production
```

## 6. 登录 ACR

在 ACR 控制台的“访问凭证”页面获取登录名并设置 Registry 密码。服务器使用 VPC 地址登录：

```bash
sudo docker login \
  --username YOUR_ACR_LOGIN_NAME \
  crpi-iyetp24mk5qki59e-vpc.cn-guangzhou.personal.cr.aliyuncs.com
```

根据提示输入 Registry 密码。不要把密码写在命令行中。新版 ACR 个人版的 VPC 地址也需要登录凭证。

## 7. 首次部署

Gitee Go 首次构建完成后，在构建记录或 ACR 镜像版本页面找到构建编号，例如 `build-12`：

```bash
cd /opt/oral-sp
sudo ./deploy/container-deploy.sh build-12
sudo ./deploy/container-compose.sh ps
```

部署脚本会依次执行：

1. 从 ACR 拉取同一版本的三个镜像。
2. 如果 SQLite 已存在，创建在线备份并校验完整性。
3. 暂停 API，使用新镜像执行数据库迁移。
4. 启动全部容器并等待健康检查。
5. 成功后把 `.env.deploy` 中的 `IMAGE_TAG` 更新为当前版本。

首次创建管理员：

```bash
sudo ./deploy/container-manage.sh createsuperuser
```

## 8. 配置 Nginx 和 HTTPS

首次申请证书前安装 HTTP 配置：

```bash
cd /opt/oral-sp
sudo install -d -m 755 /var/www/certbot
sudo install -m 644 deploy/nginx/oral-sp-container-http.conf /etc/nginx/sites-available/oral-sp
sudo ln -s /etc/nginx/sites-available/oral-sp /etc/nginx/sites-enabled/oral-sp
sudo unlink /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

申请双域名证书：

```bash
sudo certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --cert-name oral-sp \
  --domain wenzhen.wishine.top \
  --domain manage.wishine.top \
  --email YOUR_CERTIFICATE_EMAIL \
  --agree-tos \
  --no-eff-email
```

切换 HTTPS 配置：

```bash
cd /opt/oral-sp
sudo install -m 644 deploy/nginx/oral-sp-container.conf /etc/nginx/sites-available/oral-sp
sudo install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
sudo install -m 755 deploy/certbot-reload-nginx.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

仅对公网开放安全组端口 `80`、`443`，以及限定管理员来源 IP 的 `22`。不要开放 `8000`、`5173` 或 `5174`。

## 9. 日常发布与回滚

正常发布：提交到 `main` 后，等待 Gitee Go 自动完成三个镜像的测试、构建和推送。在流水线记录中确认构建编号，例如 `12`，然后 SSH 登录 ECS 发布对应的 `build-12`：

```bash
cd /opt/oral-sp
git pull --ff-only origin main
sudo ./deploy/container-deploy.sh build-12
```

应用代码回滚可重新部署之前的镜像版本：

```bash
sudo ./deploy/container-deploy.sh build-11
```

数据库迁移不一定能通过切换旧镜像自动撤销。涉及数据库结构变更时，应先停止服务，再根据迁移兼容性决定是否恢复 `/opt/oral-sp/backups/` 中的 SQLite 备份。

## 10. 常用排查命令

```bash
cd /opt/oral-sp
sudo ./deploy/container-compose.sh ps
sudo ./deploy/container-compose.sh logs --tail 200 api
sudo ./deploy/container-compose.sh logs --tail 100 web-student web-teacher
sudo docker stats --no-stream
curl --fail https://wenzhen.wishine.top/api/health/ready/
curl --fail https://manage.wishine.top/api/health/ready/
```

- `unauthorized`：检查登录的是 VPC 地址、使用的是 Registry 独立密码。
- `manifest unknown`：确认三个仓库都有完全相同的 `build-N` 标签。
- `database is locked`：记录并发情况，准备迁移 PostgreSQL。
- 容器被系统杀死：检查 `free -h`、`swapon --show`、`dmesg -T | tail`。

## 官方参考

- [Gitee Go 镜像构建](https://help.gitee.com/gitee-go/plugin/image-build-and-deployment)
- [ACR 个人版推送与拉取](https://help.aliyun.com/zh/acr/user-guide/use-a-container-registry-personal-edition-instance-to-push-and-pull-images)
- [新版 ACR 个人版访问域名](https://help.aliyun.com/zh/acr/user-guide/individual-edition-instance-independent-domain-name-capacity-limit)
- [Docker Engine 安装到 Debian](https://docs.docker.com/engine/install/debian/)
