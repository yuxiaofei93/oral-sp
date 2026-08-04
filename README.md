# 口腔门诊 AI 模拟问诊系统

面向口腔医学教学的 AI 标准化患者（AI-SP）MVP。系统以结构化病例、分阶段问诊、受控资料释放和可追溯评分为核心，不用于真实患者诊疗。

## 当前进度

当前已完成阶段 0–3 的基础闭环：

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
- 教师任务发布、班级名单快照、统一收卷和反馈发布 API。
- 学生任务列表、一次作答限制、服务端整场计时和不可回退阶段状态机。
- 不可修改/删除的问诊消息、客户端幂等消息编号和模型调用审计。
- Mock 与 OpenAI-compatible 两种患者模型网关；诊断泄露时回退规则回答。
- 学生问诊工作台、四阶段提交和延迟反馈查看。

尚未实现自动评分、遗漏/错误项分析、教师端任务发布页面、班级管理页面和数据清理任务。当前反馈接口先返回标准诊断、标准检查和评分功能占位信息。

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

MVP 当前通过 Django Admin 维护课程、班级、教师关系和学生名单。教师任务 API 位于 `/api/teacher/assignments/`；后续阶段会补对应的可视化页面。

## 患者模型配置

本地开发默认使用确定性的 `mock` 网关，不访问互联网。接入外部模型时，在服务端 `.env` 中设置：

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://供应商接口地址/v1
LLM_API_KEY=只保存在服务器上的密钥
LLM_MODEL=供应商模型名称
LLM_TIMEOUT_SECONDS=30
```

网关调用 `/chat/completions`，要求供应商兼容该接口和 JSON object 响应格式。发送给模型的上下文只包含本次问题命中的患者事实，不包含标准诊断、标准检查解释或评分答案；数据库保存调用哈希、命中事实编码、耗时、token 数和错误码，不额外保存完整提示词。

## 低配部署说明

1 核 1 GB 主机只运行一个 API worker，并把 PostgreSQL 最大连接数限制为 30。MVP 不在同一台机器运行 MinIO、Redis、Celery或本地大模型。建议配置 1–2 GB swap，并在真实课堂前用预期人数进行一次并发测试。

外部模型密钥只能通过服务端环境变量提供，不能提交到 Git、返回给浏览器或记录到日志。
