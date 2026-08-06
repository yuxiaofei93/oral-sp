# 邮箱认证与本地验证码测试

## 本地开发

默认邮件后端是 `django.core.mail.backends.console.EmailBackend`。保持 `.env` 中以下配置即可：

```dotenv
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=口腔模拟问诊系统 <no-reply@example.com>
```

启动后端后，在学生注册页或任一登录页点击“获取验证码”。API 终端会打印邮件主题、收件人和正文，正文中的六位数字就是验证码；本地模式不会真的连接收件邮箱。

## 部署 SMTP

拿到邮件服务信息后，在服务器 `.env` 中填写：

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=你的SMTP账号
EMAIL_HOST_PASSWORD=你的SMTP密码或授权码
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_TIMEOUT_SECONDS=10
DEFAULT_FROM_EMAIL=口腔模拟问诊系统 <no-reply@你的域名>
```

端口 587 通常使用 TLS，端口 465 通常使用 SSL；`EMAIL_USE_TLS` 和 `EMAIL_USE_SSL` 不能同时设为 `true`。配置后重启 API 服务。

## 接口与安全边界

- `POST /api/auth/verification-codes/registration/`：发送注册验证码。
- `POST /api/auth/register/`：校验验证码并创建学生账号、角色及班级关系。
- `POST /api/auth/verification-codes/password-reset/`：发送重置密码验证码；无论账号是否存在都返回统一文案。
- `POST /api/auth/password-reset/`：校验验证码并设置新密码。

所有写接口需要 CSRF Token。验证码有效期为 10 分钟，同一邮箱 60 秒内不能重复获取，最多允许 5 次错误尝试。验证码明文只通过邮件后端发送，数据库仅保存不可直接还原的摘要。
