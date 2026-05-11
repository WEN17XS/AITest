# AITestHub 项目总览

## 项目定位

AITestHub 是一个面向未来多个项目接入的 Agent + 人工审核自动化测试平台。平台目标不是单一测试脚本工具，而是统一管理：

- 需求输入
- Agent 生成测试用例
- 人工审核和编辑测试用例
- 测试环境配置
- 测试知识库
- 测试任务执行
- 测试报告
- CI/CD 触发入口

当前仍处于第一阶段：平台闭环补强。

## 当前阶段

第一阶段目标是让平台具备完整的“生成、审核、执行、报告”最小闭环。

当前已经完成：

- FastAPI 后端基础结构
- React + TypeScript 前端工作台
- PostgreSQL + pgvector 数据库
- Redis + Celery 异步任务
- Alembic 数据库迁移
- DeepSeek 大模型接入
- `langchain-deepseek` Agent 生成测试用例
- 需求生成可识别页面点击、搜索框、按钮、跳转等 Web UI 场景并生成 `web_ui` 用例
- 测试用例人工审核
- 测试用例编辑
- 管理员删除项目
- 项目环境配置
- 知识库录入和关键词查询
- 文件上传批量导入需求、历史缺陷、业务规则和测试策略到知识库
- 基于知识库 skill 上下文辅助生成测试用例
- AI 自评审生成用例，输出遗漏、矛盾、越界、重复和建议
- 人工审核后自动沉淀通过用例或反例经验到知识库
- 测试任务异步执行
- 测试报告写回数据库
- CI/CD webhook 入口
- 前端顶部导航和多功能页面切换
- 登录注册、Bearer Token 鉴权和基础角色权限
- 测试报告详情视图
- CI 触发记录查询和详情展示

当前测试执行器仍是模拟执行器。也就是说，平台闭环已经跑通，但还没有真正接入 Playwright、pytest 或其他真实测试框架。

## 技术栈

后端：

- FastAPI
- SQLAlchemy
- Alembic
- Celery
- Redis
- PostgreSQL
- pgvector
- Playwright
- LangChain
- langchain-deepseek

前端：

- React
- TypeScript
- Vite
- lucide-react

基础设施：

- Docker Compose
- PostgreSQL + pgvector 镜像
- Redis 镜像

## 关键目录

```text
backend/
  app/
    api/routes/          后端 API 路由
    core/                配置读取
    db/                  数据库模型和会话
    services/            Agent、LLM、知识库、测试执行等服务
      executors/         第二阶段测试执行器接口、注册表和具体执行器
    workers/             Celery 任务
  migrations/            Alembic 迁移
  requirements.txt       后端依赖

frontend/
  src/
    api/client.ts        前端 API 客户端
    App.tsx              前端主界面和导航视图
    styles.css           前端样式

docs/
  architecture.md        架构设计
  executor-architecture.md 第二阶段测试执行器架构设计
  api.md                 API 说明
  cicd.md                CI/CD 接入说明
  roadmap.md             路线图

docker-compose.yml       数据库和 Redis
README.md                启动说明
```

## 后端模块说明

主要 API：

- `projects`：项目管理
- `environments`：项目环境配置
- `requirements`：需求录入和用例生成
- `test-cases`：测试用例创建、编辑、审核
- `runs`：测试任务创建和查询
- `knowledge`：知识库录入和查询
- `ci`：CI/CD webhook
- `llm`：DeepSeek 大模型健康检查
- `auth`：注册、登录、当前用户信息

主要服务：

- `auth_service.py`：密码哈希、密码校验、JWT token 创建和解析。密码哈希使用标准库 PBKDF2-HMAC，避免 Python 3.14 下 bcrypt 二进制兼容问题。
- `llm_service.py`：通过 `langchain-deepseek` 初始化 `ChatDeepSeek`
- `agent_service.py`：测试用例生成 Agent
- `agent_service.py` 同时包含用例自评审能力：DeepSeek 可用时由 `deepseek-reviewer` 输出结构化评审，不可用时由规则评审兜底。
- `agent_service.py` 生成规则已支持 `web_ui` 和 `api` 类型识别；页面点击、搜索框、按钮、跳转等需求会生成 Playwright 受控步骤，接口/HTTP/状态码类需求会生成 `api` 用例。
- `execution_service.py`：测试执行编排服务，负责状态流转、用例选择、执行器分发和结果落库。
- `executors/`：第二阶段执行器包，已包含 `TestExecutor` 接口、`ExecutionContext` / `ExecutionResult` 标准对象、`ExecutorRegistry`、`MockExecutor` 和 `PlaywrightExecutor`。当前默认手动/API/集成类型仍使用 `MockExecutor`，`web_ui` 类型可由 `playwright` 执行器执行。
- `knowledge_service.py`：知识库写入、skill 上下文召回、审核反馈沉淀服务
- `knowledge_import_service.py`：解析 txt、md、csv、json 上传文件并批量写入知识库

第二阶段执行器架构已设计并开始落地，详见 `docs/executor-architecture.md`。长期方向是将执行层拆分为运行编排层、执行器注册表、具体执行器和结果/附件持久化；`execution_service.py` 保留为编排入口，当前模拟执行器已迁移为 `MockExecutor`，并继续作为闭环兜底能力。

权限约定：

- 第一个注册用户自动成为 `admin`。
- 后续注册用户默认为 `tester`。
- `admin` 和 `reviewer` 可以通过或驳回测试用例。
- 只有 `admin` 可以删除项目。
- `tester` 可以创建、编辑和执行测试，但不能审核测试用例。
- 账号只能包含英文字母、数字、下划线，长度 4-32 位；密码长度 8-64 位，不能包含空白字符，且必须同时包含字母和数字。

## 前端页面结构

前端已经从单页堆叠改成顶部导航式工作台。

导航包含：

- 总览
- 需求生成
- 人工审核
- 测试执行
- 知识库
- 环境配置
- 登录页

页面结构：

- 登录前：注册/登录表单，前端会先做账号和密码边界校验。
- 顶部：平台标题、当前用户、退出登录、项目选择、刷新按钮
- 导航：切换不同功能视图
- 项目摘要条：当前项目、默认分支、环境数量
- 左侧：项目管理
- 右侧：当前功能页面
- 项目管理：`admin` 可删除项目，删除会级联移除该项目下需求、用例、运行记录、环境、知识和 CI 触发记录。
- 测试执行页：左侧展示测试运行和 CI 触发记录，右侧展示运行详情、报告正文、用例日志和关联 CI payload。
- 测试执行页已支持手动选择 `mock` / `playwright` 执行器、项目环境、Playwright headless 和 timeout 参数；选择 Playwright 时只提交已通过的 `web_ui` 用例。
- 人工审核编辑页支持通过下拉框修改用例类型为 UI 自动化、接口/API、功能、回归、安全或人工；步骤编辑框支持 JSON 数组，便于保留 Playwright 的 selector、value、url、text 等字段。
- 知识库页：支持单条录入，也支持上传 txt、md、csv、json 批量导入需求、历史缺陷、业务规则和测试策略。

## 数据库

当前迁移版本：

```text
20260511_0006
```

主要表：

- `users`
- `projects`
- `project_environments`
- `requirements`
- `test_cases`
- `test_runs`
- `test_run_results`
- `test_run_artifacts`
- `knowledge_chunks`
- `ci_triggers`

`knowledge_chunks` 已预留 `embedding vector(1536)` 字段，后续可以接入真实 embedding 和向量检索。

第二阶段执行器运行配置字段：

- `test_runs.executor_type`：本次运行使用的执行器，当前默认 `mock`。
- `test_runs.environment_id`：本次运行绑定的项目环境，可为空；为空时编排层尝试使用项目默认环境。
- `test_runs.executor_config`：本次运行级执行器配置。
- `test_runs.error_message`：执行器初始化、环境准备或系统异常时的错误摘要。

测试运行附件模型：

- `test_run_artifacts.run_id`：所属测试运行。
- `test_run_artifacts.result_id`：可选，绑定到单条用例执行结果；为空表示运行级附件。
- `test_run_artifacts.artifact_type`：附件类型，例如 `log`、`screenshot`、`video`、`trace`、`report`。
- `test_run_artifacts.path`：相对存储路径，不保存本机绝对路径。
- 本地执行产物目录约定为 `backend/storage/runs/{run_id}/`，该目录已加入 `.gitignore`。

知识反馈闭环字段：

- `test_cases.ai_review`：保存 AI 自评审结果。
- `knowledge_chunks.status`：知识状态，建议使用 `candidate`、`active`、`verified`、`rejected`。
- `knowledge_chunks.skill_name`：知识所属测试 skill。
- `knowledge_chunks.triggers`：触发关键词。
- `knowledge_chunks.quality_score`：1-5 分，生成时优先召回高分知识。

审核沉淀规则：

- 审核通过的人工用例沉淀为 `approved_test_case`。
- 审核通过的 AI 生成用例沉淀为 `reviewed_test_case`。
- 驳回用例沉淀为 `anti_pattern`，用于后续提示 Agent 避免类似问题。

## 当前端口

由于本机已有 PostgreSQL 和 Redis 占用默认端口，本项目使用：

- PostgreSQL：`localhost:5433`
- Redis：`localhost:6380`
- 前端：`http://localhost:5173`
- 后端当前验证端口：`http://localhost:8001`

前端默认 API 地址已经指向：

```text
http://localhost:8001/api/v1
```

本地开发 CORS 已允许 Vite 常见开发端口 `5173-5179` 的以下前端来源：

- `http://localhost:<port>`
- `http://127.0.0.1:<port>`
- `http://0.0.0.0:<port>`

## 环境变量

`.env` 中需要关注：

```env
DATABASE_URL=postgresql+psycopg://aitest:aitest@localhost:5433/aitesthub
REDIS_URL=redis://localhost:6380/0

LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=你的模型

WEBHOOK_SECRET=change-me
AUTH_SECRET=请替换为足够长的随机字符串
```

不要把 `.env` 提交到版本库。

## 常用启动命令

启动数据库和 Redis：

```powershell
docker compose up -d db redis
```

启动后端：

```powershell
cd backend
..\.venv\Scripts\activate
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

启动 Celery Worker：

```powershell
cd backend
..\.venv\Scripts\activate
celery -A app.workers.celery_app worker --loglevel=info -P solo -Q aitesthub
```

首次使用 Playwright 执行器前安装浏览器：

```powershell
cd backend
..\.venv\Scripts\activate
playwright install chromium
```

启动前端：

```powershell
cd frontend
npm run dev
```

## 已验证事项

已经验证：

- 前端 `npm run build` 通过
- 后端 Python 编译检查通过
- 第二阶段执行器基础包导入检查通过，`TestExecutionService` 已可通过默认注册表调度 `MockExecutor`
- Playwright 最小执行器已接入注册表，执行器名称为 `playwright`，支持 `web_ui` 用例的 `goto`、`click`、`fill`、`expect_text`、`expect_url` 受控动作
- 前端测试执行页已可选择 `mock` / `playwright`、项目环境、headless 和 timeout，并在运行详情展示执行器、错误信息和附件路径
- 需求“点击搜索框，搜索某关键词”已可由规则生成器产出 `web_ui` 用例和 Playwright 步骤；人工审核页可修改用例类型并保留结构化步骤
- Alembic head 已更新到 `20260511_0006`
- DeepSeek LangChain 健康检查可用
- Agent 生成用例返回 `generated_by=deepseek-agent`
- 前端导航切换正常
- 新版前端页面在浏览器中可打开
- 非法中文/特殊符号账号注册返回 `422`
- 未登录访问受保护接口返回 `401`
- 第一个注册用户为 `admin`，后续注册用户为 `tester`
- `tester` 调用审核接口返回 `403`
- `tester` 删除项目返回 `403`，`admin` 可以删除项目
- CI webhook 可以创建测试运行和 CI 触发记录，运行详情可以返回关联 `ci_trigger`
- 知识 skill 可参与用例生成，生成结果包含 `ai_review`
- 人工审核通过后可自动沉淀 `reviewed_test_case` 知识
- 文件上传导入可将 Markdown 历史缺陷文档切分为多条 `historical_defect` skill 知识

## 当前限制

当前仍然存在的限制：

- 测试执行器是模拟执行器
- 知识库当前是关键词/skill 召回，还不是向量检索
- 登录/权限系统仍是基础版本，还没有用户管理、角色分配、禁用账号和刷新 token
- 测试报告详情页仍是文本和结构化结果展示，还没有附件、截图、视频和失败归因
- CI 触发记录已可查询和展示，但还没有回写流水线状态或 PR 评论
- 没有真实测试环境变量注入执行器
- 文件上传当前支持文本类格式，还不支持 Word/PDF 解析

## 下一步建议

在进入真实测试执行器之前，建议先完成第一阶段剩余补强：

1. 用户管理和角色分配
2. Word/PDF 需求文档解析
3. 知识库向量检索
4. Agent 生成过程日志和自评审详情页
5. 测试报告附件模型
6. CI 状态回写和质量门禁

第二阶段建议接入真实执行能力：

1. 为 Playwright 执行器补充 trace、控制台日志和视频录制。
2. 接入 pytest/API 执行器。
3. 增加失败重跑、flaky 用例识别和失败归因 Agent。

## 开发注意事项

- 代码注释和文档使用中文。
- 不要提交 `.env`、`.venv`、`node_modules`、`dist`。
- 后端新增表结构时使用 Alembic 迁移。
- DeepSeek 不可用时，Agent 应保留规则生成兜底。
- 前端功能应优先放入已有导航视图，不要再把所有功能堆到一个页面。
- 真实测试执行器接入前，不要移除当前模拟执行器；它是平台闭环的兜底验证能力。
