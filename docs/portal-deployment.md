# 学生端与教师端独立入口

## 本地测试

后端仍监听 `8000`，两个 Vite 开发服务分别代理同一套 `/api/`：

```bash
npm --prefix apps/web run dev:student  # http://localhost:5173/
npm --prefix apps/web run dev:teacher  # http://localhost:5174/
```

浏览器 Cookie 不区分端口，因此同一个浏览器中的两个 localhost 端口会共享登录状态。需要同时以教师和学生身份测试时，可使用两个浏览器或无痕窗口。

## 生产域名

推荐准备两个完整 HTTPS 地址，例如：

```dotenv
STUDENT_WEB_ORIGIN=https://student.example.com
TEACHER_WEB_ORIGIN=https://teacher.example.com
DJANGO_ALLOWED_HOSTS=student.example.com,teacher.example.com,api
DJANGO_CSRF_TRUSTED_ORIGINS=https://student.example.com,https://teacher.example.com
DJANGO_SECURE_COOKIES=true
```

不使用 Docker 时，先提供两个入口根地址，再分别构建固定入口的静态产物：

```bash
export VITE_STUDENT_ORIGIN=https://student.example.com
export VITE_TEACHER_ORIGIN=https://teacher.example.com
npm --prefix apps/web run build:student
npm --prefix apps/web run build:teacher
```

产物分别位于 `apps/web/dist/student/` 和 `apps/web/dist/teacher/`，部署时不要让第二次构建覆盖第一次构建。

Docker Compose 会构建 `web-student` 和 `web-teacher` 两个服务。生产反向代理应把学生域名指向 `web-student:80`，教师域名指向 `web-teacher:80`；两个服务都把同源 `/api/` 请求转发至同一个 Django API。

浏览器页面统一从 `/` 进入，不使用 `/student/` 或 `/teacher/`。后端 API 继续保留 `/api/student/` 和 `/api/teacher/` 前缀，这是接口授权边界，不是面向用户的入口地址。
