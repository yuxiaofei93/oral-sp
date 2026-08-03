# 口腔门诊 AI 模拟问诊系统

面向口腔医学教学的 AI 标准化患者（AI-SP）MVP。系统以结构化病例、分阶段问诊、受控资料释放和可追溯评分为核心，不用于真实患者诊疗。

## 当前进度

当前已完成阶段 0–2 的基础闭环：

- React + TypeScript 前端。
- Django + Django REST Framework 后端。
- PostgreSQL 开发数据库。
- 本地私有媒体存储，不依赖 S3 或 MinIO。
- 适配 1 核 1 GB 主机的单 worker 和低内存数据库配置。
- API 存活及数据库就绪检查。
- 手机号加密码的注册、登录、退出和当前用户接口。
- 学生、教师、管理员角色及课程、班级基础数据模型。
- 教师病例列表和七步式结构化病例编辑器。
- 患者事实、文字检查结果、诊断和评分规则编辑。
- 乐观锁草稿保存、内容哈希、幂等发布和不可变版本快照。

尚未实现学生问诊会话、外部模型网关、自动评分、反馈发布和数据清理任务。

产品需求见 [oral-clinic-ai-product-design.md](./oral-clinic-ai-product-design.md)。已确认当前项目没有 `AGENTS.md`。

## 目录

```text
apps/
  api/       Django API 和领域模块
  web/       React 学生端和教师端
docs/
  decisions/ 已确认的架构和产品决策
compose.yaml PostgreSQL、API 和 Web 开发/部署基线
```

## 本地开发

安装后端依赖并运行测试：

```bash
make api-install
make api-test
```

安装前端依赖并运行测试：

```bash
make web-install
make web-test
make web-build
```

有 Docker Compose 的环境可以启动完整服务：

```bash
cp .env.example .env
docker compose up --build
```

启动后访问：

- Web：`http://localhost`
- API 存活检查：`http://localhost/api/health/live/`
- API 就绪检查：`http://localhost/api/health/ready/`
- 获取 CSRF Token：`http://localhost/api/auth/csrf/`

教师和管理员登录后可进入结构化病例编辑器。自助注册账号默认只有学生角色；教师和管理员由 Django Admin 授权。

## 低配部署说明

1 核 1 GB 主机只运行一个 API worker，并把 PostgreSQL 最大连接数限制为 30。MVP 不在同一台机器运行 MinIO、Redis、Celery或本地大模型。建议配置 1–2 GB swap，并在真实课堂前用预期人数进行一次并发测试。

外部模型密钥只能通过服务端环境变量提供，不能提交到 Git、返回给浏览器或记录到日志。
