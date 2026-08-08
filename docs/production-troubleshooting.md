# 生产问题定位手册

生产 API 将应用日志以单行 JSON 写到标准输出，由 systemd journal 统一保存。Nginx 继续保存入口访问日志和代理错误日志。业务日志不记录验证码、密码、SMTP 授权码或完整邮箱地址。

## 用户需要提供的信息

页面出现服务端错误时会显示 `问题编号`。排查时优先收集：

1. 问题编号。
2. 大致发生时间和所用域名。
3. 当时执行的操作，例如“学生注册获取验证码”。
4. 页面错误文案；不要提供密码或验证码。

每个 API 响应也会携带 `X-Request-ID` 响应头。没有传入合法请求 ID 时，API 自动生成一个 32 位 ID；同一次请求产生的业务日志和请求完成日志使用同一编号。

## 快速查询

查询最近一小时 API 日志：

```bash
sudo journalctl -u oral-sp-api --since "1 hour ago" --no-pager -o cat
```

按用户提供的问题编号查询完整链路：

```bash
sudo journalctl -u oral-sp-api --since "24 hours ago" --no-pager -o cat \
  | grep -F '替换为问题编号'
```

查询最近的验证码邮件失败：

```bash
sudo journalctl -u oral-sp-api --since "24 hours ago" --no-pager -o cat \
  | grep -F '"event":"verification_email.failed"'
```

查询请求级 5xx：

```bash
sudo journalctl -u oral-sp-api --since "24 hours ago" --no-pager -o cat \
  | grep -E '"event":"request.completed".*"status_code":5[0-9][0-9]'
```

Nginx 入口和代理错误：

```bash
sudo tail -n 200 /var/log/nginx/access.log
sudo tail -n 200 /var/log/nginx/error.log
```

## 邮件事件字段

- `verification_email.started`：已经创建验证码记录，开始调用邮件后端。
- `verification_email.sent`：邮件后端报告投递成功。
- `verification_email.failed`：邮件后端抛出异常或报告投递数量异常。
- `request_id`：与页面问题编号对应。
- `email_ref`：完整邮箱的不可逆短摘要，可判断多条日志是否属于同一邮箱。
- `error_type`、`error_message`、`stack_trace`：SMTP 失败类型、脱敏原因和调用栈。
- `backend`、`smtp_host`、`smtp_port`、`use_tls`、`use_ssl`：实际生效的非敏感邮件配置。

`verification_email.sent` 只表示 SMTP/邮件后端已接受消息，不保证收件服务最终进入主收件箱。若已记录成功但用户没有收到，应继续检查退信、垃圾箱、发件域名 SPF/DKIM/DMARC 和邮件供应商投递记录。

## 部署前配置检查

以下命令会运行 Django 系统检查：

```bash
sudo -u www-data ./deploy/manage-production.sh check --deploy
```

生产环境使用控制台邮件后端、SMTP 配置缺失，或同时启用 TLS 和 SSL 时，检查会失败并给出 `oral_sp.E001`、`oral_sp.E002` 或 `oral_sp.E003`。自动更新脚本在重启 API 前也会执行该检查，避免把明显错误的邮件配置部署上线。

修改 `.env.production` 后必须重启服务：

```bash
sudo systemctl restart oral-sp-api
sudo systemctl status oral-sp-api --no-pager
```

## 日志边界

应用日志适合定位 API、数据库、SMTP 和模型调用故障，但不能替代外部供应商的投递记录。服务器必须保留合理的 journal 容量和时间；如果 `journalctl --list-boots` 只显示当前启动或历史很短，应检查 journald 的持久化与容量配置。
