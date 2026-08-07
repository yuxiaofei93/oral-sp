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
VITE_STUDENT_ORIGIN=https://student.example.com
VITE_TEACHER_ORIGIN=https://teacher.example.com
DJANGO_ALLOWED_HOSTS=student.example.com,teacher.example.com,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://student.example.com,https://teacher.example.com
DJANGO_SECURE_COOKIES=true
```

服务器本地编译时，先提供两个入口根地址，再分别构建固定入口的静态产物：

```bash
export VITE_STUDENT_ORIGIN=https://student.example.com
export VITE_TEACHER_ORIGIN=https://teacher.example.com
npm --prefix apps/web run build:student
npm --prefix apps/web run build:teacher
```

产物分别位于 `apps/web/dist/student/` 和 `apps/web/dist/teacher/`。当前内测服务器的 Nginx 将两个域名分别指向对应的静态目录，并把同源 `/api/` 请求转发到 `127.0.0.1:8010` 的 Django API；`8000` 保留给同机现有服务。

浏览器页面统一从 `/` 进入，不使用 `/student/` 或 `/teacher/`。后端 API 继续保留 `/api/student/` 和 `/api/teacher/` 前缀，这是接口授权边界，不是面向用户的入口地址。
