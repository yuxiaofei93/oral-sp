# 口腔门诊 AI 模拟问诊系统

面向口腔医学教学的 AI 标准化患者（AI-SP）MVP。系统以结构化病例、单阶段问诊、受控资料释放和可追溯评分为核心，不用于真实患者诊疗。

## 当前进度

当前已完成阶段 0–9 的基础闭环：

- React + TypeScript 前端。
- Django + Django REST Framework 后端。
- SQLite 本地开发和内测数据库，并保留 PostgreSQL 适配能力。
- 本地私有媒体存储，不依赖 S3 或 MinIO。
- 适配 1 核 1 GB 主机的单 worker 和低内存数据库配置。
- API 存活及数据库就绪检查。
- JSON 应用日志、请求问题编号、邮件投递事件和生产配置检查。
- 邮箱验证码注册、邮箱加密码登录、忘记密码和当前用户接口。
- 学生、教师、管理员角色及班级基础数据模型。
- 教师病例列表和七步式结构化病例编辑器。
- 患者事实、文字检查结果、诊断和评分规则编辑。
- 乐观锁草稿保存、内容哈希、幂等发布和不可变版本快照。
- 教师任务发布、班级名单快照、结束任务和反馈发布 API。
- 学生任务列表、一次作答限制、服务端整场计时和单次最终交卷。
- 不可修改/删除的问诊消息、客户端幂等消息编号和模型调用审计。
- Mock、DeepSeek 与通用 OpenAI-compatible 患者模型网关；诊断泄露时回退规则回答。
- 学生问诊工作台、版本化病例草稿自动保存、单份病例交卷和延迟反馈查看。
- 交卷前始终可用的口腔体格检查申请、患者同意、私有图片/附件释放和可追溯评分。
- 教师班级页面，以及学生自助选班和教师名单管理。
- 教师问诊任务页面，包括病例版本选择、名单快照、作答进度、结束任务和反馈发布。
- 病史事实、标准诊断、检查选择和病例字段关键词的确定性规则评分。
- 每个评分项保存消息或病例记录证据，教师可以查看单个学生完整答卷。
- 学生在反馈发布后查看自动得分、待评价分值、遗漏项、错误项和标准答案。
- 教师可逐项复核自动分或待评价项，并填写必需的改分理由和总体评语。
- 每次复核生成不可覆盖的审计版本；反馈发布后成绩和评语冻结。
- 教师答卷页按问诊任务展示完成率、平均得分率、平均分、平均用时、高频遗漏和常见错误。
- 教师可导出带 UTF-8 BOM 的 CSV 名单与成绩明细，导出内容采用表格公式注入防护。
- 会话从交卷或超时结束时保留 180 天，并提供默认只预览、显式确认才删除的清理命令。

尚未实现跨任务统计筛选。规则无法可靠判定的评分项会明确标记为“待评价”，由教师复核赋分；患者模型不会生成学生分数。

产品需求见 [oral-clinic-ai-product-design.md](./oral-clinic-ai-product-design.md)。已确认当前项目没有 `AGENTS.md`。

## 目录

```text
apps/
  api/       Django API 和领域模块
  web/       React 学生端和教师端
docs/
  decisions/ 已确认的架构和产品决策
deploy/      Gunicorn、Nginx、前端构建和 SQLite 备份脚本
```

## 本地开发

首次准备环境：

```bash
test -f .env || cp .env.example .env
make api-install
make web-install
```

启动后端前先加载本地环境变量并初始化 SQLite：

```bash
set -a
source .env
set +a

.venv/bin/python apps/api/manage.py migrate
.venv/bin/python apps/api/manage.py runserver 0.0.0.0:8000
```

在另外两个终端分别启动学生端和教师端：

```bash
npm --prefix apps/web run dev:student
npm --prefix apps/web run dev:teacher
```

启动后访问：

- 学生登录与注册：`http://localhost:5173/`
- 教师与管理员登录：`http://localhost:5174/`
- API 存活检查：`http://localhost:5173/api/health/live/`
- API 就绪检查：`http://localhost:5173/api/health/ready/`
- 获取 CSRF Token：`http://localhost:5173/api/auth/csrf/`

学生端与教师端使用独立根地址，不再通过 `/student/` 和 `/teacher/` 页面路径区分。教师和管理员从教师入口登录后可进入病例库、班级管理、问诊任务三个工作区。自助注册仅在学生入口开放，学生必须选择一个当前有效的班级，注册成功后会自动加入该班；教师和管理员由 Django Admin 授权。入口隔离只负责交互引导，后端 API 仍会独立校验每个账号的角色权限。

运行全部测试和本地构建：

```bash
make api-test
make api-lint
make web-test
make web-build
```

生产环境由服务器本地运行 `./deploy/build-frontends.sh`，分别生成 `apps/web/dist/student/` 和 `apps/web/dist/teacher/`。如更换域名，通过 `VITE_STUDENT_ORIGIN`、`VITE_TEACHER_ORIGIN` 指定两个完整 HTTPS 根地址。Django 的 `DJANGO_ALLOWED_HOSTS` 和 `DJANGO_CSRF_TRUSTED_ORIGINS` 也要包含这两个域名。页面入口不再使用角色路径，但后端 `/api/student/`、`/api/teacher/` 命名空间会继续保留用于权限隔离。

## 最小教学流程

1. 管理员在 Django Admin 中创建教师账号或添加教师角色；MVP 暂不开放教师自助注册。
2. 教师在“班级管理”直接创建班级。
3. 学生使用邮箱验证码自助注册并选择班级，系统自动把学生加入该班。
4. 教师可在“班级管理”查看正常和已冻结班级，冻结或重新激活班级，并将学生移出班级或转入自己管理的另一个正常班级。班级状态和转班不会改变已经发布任务的名单快照。
5. 教师在“病例库”完成结构化病例编辑并发布不可变版本。
6. 教师在“问诊任务”中选择病例版本和班级，设置开放时间、最晚截止时间和整场限时。
7. 学生开始后仅有一次作答机会；问诊与病例编辑在交卷前同时开放，病例草稿自动保存，最终只提交一次。教师可查看未开始、作答中、已交卷和已超时人数。
8. 教师在答卷详情中检查规则评分，必要时逐项复核教师评价项或调整规则分。
9. 教师结束任务后再发布反馈，学生随后才能看到成绩、评语、标准诊断和标准检查。

任务发布时复制班级名单快照，之后调整班级只影响未来任务。

## 本地邮箱验证码

默认 `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`，不会向真实邮箱发信。点击“获取验证码”后，六位验证码会完整输出在正在运行 Django API 的终端中。部署测试服务时再把 `EMAIL_BACKEND` 切换为 SMTP，并填写 `.env.example` 中的邮件服务变量；前端和业务接口无需再次修改。

## DeepSeek 模型配置

本地开发默认使用确定性的 `mock` 网关，不访问互联网。接入 DeepSeek 时，在服务端 `.env` 中设置：

```dotenv
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-替换为你自己的密钥
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=30
```

不要把真实密钥提交到仓库或粘贴到聊天中。本地启动前加载项目根目录的 `.env`；修改后需重新加载环境变量并重启 API 服务。

患者问答采用两步模型调用：语义路由先根据当前问题、本次问诊的全部学生与患者历史消息以及所有允许披露的患者事实内容选择事实编码，患者回答模型随后只能使用选中的事实作答。事实内容被视为病历式语义笔记，回答模型必须先理解再改写为第一人称、短句式的日常口语，不得直接朗读或拼接原文；检测到照抄时会纠正一次，仍不合格则使用受控的口语化规则回答。路由不接收标准诊断、标准检查解释、评分答案、学生姓名或邮箱。系统不使用大模型评价学生或生成分数；评分仅由确定性规则和教师复核完成。数据库保存患者模型调用的命中事实、模型、耗时、token 数和错误码，不保存完整提示词或思维链。

接口行为、数据边界和故障处理见 [DeepSeek 接入说明](./docs/deepseek-integration.md)。

## 低配部署说明

1 核 1 GB 主机只运行一个 API worker。MVP 不在同一台机器运行 MinIO、Redis、Celery 或本地大模型。建议配置 1–2 GB swap，并在真实课堂前用预期人数进行一次并发测试。

当前阿里云内测机采用 SQLite、Gunicorn、Nginx 和 Certbot，不需要 Docker 或 PostgreSQL。双域名、HTTPS、systemd、SQLite 备份和更新回滚流程见 [阿里云 Debian 13 原生部署文档](./docs/deployment-aliyun-debian.md)。服务器使用本地 `.env.production`，不要直接复用开发 `.env`。

页面出现服务端错误时会显示问题编号。提供问题编号、发生时间、域名和操作步骤后，可按 [生产问题定位手册](./docs/production-troubleshooting.md) 从 systemd journal 关联请求日志和业务异常。

外部模型密钥只能通过服务端环境变量提供，不能提交到 Git、返回给浏览器或记录到日志。

## 数据保留清理

先预览超过半年保留期的数据范围：

```bash
.venv/bin/python apps/api/manage.py purge_expired_simulation_data
```

确认预览范围并完成数据库备份后，显式执行：

```bash
.venv/bin/python apps/api/manage.py purge_expired_simulation_data --execute
```

详细边界和定时运行建议见 [数据保留与清理说明](./docs/data-retention.md)。
