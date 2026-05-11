# AITestHub

AITestHub 是一个面向多项目接入的 Agent + 人工审核自动化测试平台。第一阶段目标是跑通平台闭环：

- 根据需求文档或自然语言生成测试用例
- 使用 `langchain-deepseek` 接入 DeepSeek 大模型
- 人工审核、编辑、通过或驳回测试用例
- 登录注册、Bearer Token 鉴权和基础角色权限
- 配置项目测试环境
- 录入和查询测试知识库
- 基于测试 skill 知识辅助生成用例，并在生成后执行 AI 自评审
- 人工审核通过或驳回后自动沉淀正向经验或反例经验
- 执行测试任务并生成测试报告
- 查看测试报告详情和 CI 触发记录详情
- 支持 CI/CD Webhook 触发测试
- 使用 PostgreSQL 存储业务数据
- 使用 pgvector 预留向量知识库能力

## 技术栈

- 后端：FastAPI + SQLAlchemy + Alembic
- 前端：React + TypeScript + Vite
- 数据库：PostgreSQL + pgvector
- 中间件：Redis
- 异步任务：Celery
- 大模型：LangChain + langchain-deepseek
- 测试执行：内置模拟执行器，预留 Playwright / pytest 执行器

## 快速启动

### 1. 准备环境

需要安装：

- Docker Desktop
- Node.js 20+
- Python 3.11+，当前 Python 3.14 也已验证可运行

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

DeepSeek 配置示例：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

你也可以使用账号已开通的其他 DeepSeek 模型。

认证相关配置：

```env
AUTH_SECRET=请替换为足够长的随机字符串
```

注册账号规则：账号只允许英文字母、数字、下划线，长度 4-32 位；密码长度 8-64 位，不能包含空白字符，且必须同时包含字母和数字。第一个注册用户会自动成为 `admin`，后续注册用户默认为 `tester`。

### 3. 启动依赖

```powershell
docker compose up -d db redis
```

默认端口：

- PostgreSQL：`localhost:5433`
- Redis：`localhost:6380`

### 4. 启动后端

```powershell
cd backend
..\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

如果 `8000` 被旧进程占用，可以临时使用：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### 5. 启动 Celery Worker

```powershell
cd backend
..\.venv\Scripts\activate
celery -A app.workers.celery_app worker --loglevel=info -P solo -Q aitesthub
```

### 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

访问：

- 前端：`http://localhost:5173`
- 后端接口文档：`http://localhost:8000/docs`
- 大模型健康检查：`http://localhost:8000/api/v1/llm/health`

## CI/CD Webhook

```text
POST http://你的服务地址/api/v1/ci/webhook
Header: X-AITestHub-Token: WEBHOOK_SECRET
```

请求体示例：

```json
{
  "project_id": 1,
  "branch": "main",
  "commit_sha": "abc123",
  "changed_files": ["backend/app/main.py"],
  "triggered_by": "jenkins"
}
```

登录后的前端页面可以在“测试执行”导航中查看运行详情、用例结果、报告正文和关联 CI payload。

## 文档

- [架构设计](docs/architecture.md)
- [API 说明](docs/api.md)
- [CI/CD 接入说明](docs/cicd.md)
- [后续路线图](docs/roadmap.md)
