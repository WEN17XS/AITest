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
- pytest
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
- `llm_service.py`：通过 `langchain-deepseek` 初始化 `ChatDeepSeek`，并设置请求超时和有限重试，避免 LLM 网络异常长时间阻塞生成链路。
- `agent_service.py`：测试用例生成 Agent
- `agent_service.py` 同时包含用例自评审能力：DeepSeek 可用时由 `deepseek-reviewer` 输出结构化评审，不可用、网络连接异常或 API 调用异常时由规则评审兜底，避免需求生成接口直接返回 500。
- `agent_service.py` 生成规则已支持 `web_ui` 和 `api` 类型识别；页面点击、搜索框、按钮、跳转等需求会生成 Playwright 受控步骤，接口/HTTP/状态码类需求会生成 `api` 用例。
- `api_doc_parser.py`：轻量接口文档解析服务，可从中文接口文档文本中提取 `api/...` 路径、请求方式和 JSON 请求示例，用于辅助生成可执行 API 链路用例。
- `document_text_service.py`：上传文档文本提取服务，支持 txt、md、csv、json，并在安装 `pypdf` 时支持 PDF 文本提取；需求生成页可直接上传接口文档作为本次生成上下文。
- `execution_service.py`：测试执行编排服务，负责状态流转、用例选择、执行器分发和结果落库。
- `executors/`：第二阶段执行器包，已包含 `TestExecutor` 接口、`ExecutionContext` / `ExecutionResult` 标准对象、`ExecutorRegistry`、`MockExecutor`、`PlaywrightExecutor`、`ApiExecutor`、`PytestExecutor` 和 `CommandExecutor`。`web_ui` 类型默认由 `playwright` 执行器执行，`api` 类型默认由 `api` 执行器执行，`pytest` 类型默认由 `pytest` 执行器执行，`command` / `integration` 类型默认由 `command` 执行器执行，`manual` 类型仍使用 `mock` 兜底。
- `PlaywrightExecutor` 支持 `goto`、`click`、`fill`、`press`、`expect_text`、`expect_url`，导航默认等待 `domcontentloaded`，并可通过 `selector_candidates` 在主 selector 不可见时尝试候选元素；失败时会采集页面 URL、标题、body 摘要、可见输入框/按钮/链接和 selector 诊断，写入 `failure-evidence.json` 附件。
- `ApiExecutor` 支持受控步骤 `request`、`extract_json`、`expect_status`、`expect_json_contains`、`expect_text_contains`；每条用例内维护局部变量，支持从上一条 JSON 响应提取字段并通过 `${var}` 递归替换到后续请求的 URL、headers、params、json、body/form 中；项目环境 `variables` 会作为初始变量注入执行器，适合放置账号、密码、token 等敏感配置；相对 URL 会使用项目环境 `base_url`，日志会记录请求、状态码、耗时和脱敏响应摘要，URL 查询参数里的 token/password 等敏感字段也会脱敏。
- API 执行器会额外注入运行期变量 `${RUN_ID}`、`${TIMESTAMP}`、`${SHORT_TS}`，用于生成一次性测试数据；注册类用例应优先使用短后缀，避免被测系统用户名长度限制。
- `PytestExecutor` 通过非 shell 的 `subprocess.run` 调用 `python -m pytest`，支持运行级 `args` 或步骤级 `action=pytest` / `target` / `args`。
- `CommandExecutor` 通过非 shell 的 `subprocess.run` 执行参数数组形式命令，默认命令白名单为 `python`、`pytest`、`npm`、`pnpm`、`node`，可由运行级配置扩展。
- `failure_diagnosis_service.py`：测试执行失败归因服务，采用 LLM 优先、规则兜底。DeepSeek 可用时由 `llm-diagnoser` 输出结构化失败类型、根因、证据、修复建议、建议修复步骤和建议沉淀的知识类型；LLM 不可用时由规则结合日志、附件和 `failure-evidence.json` 识别 selector 不可见、导航超时、断言失败、第三方反自动化等常见错误。对于 selector fallback 成功但最终断言失败的场景，规则会尝试把 fallback selector 写回并改用 `press Enter` 提交。归因结果可由人工点击沉淀为知识库条目。
- `knowledge_service.py`：知识库写入、skill 上下文召回、审核反馈沉淀服务；需求生成会使用 `get_generation_context` 优先召回 `selector_strategy`、`execution_failure`、`site_compatibility`、`anti_pattern` 等执行经验。
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
- 测试执行页已支持手动选择 `mock`、`playwright`、`api`、`pytest`、`command` 执行器、项目环境、headless 和 timeout 参数；执行前可在可执行用例列表中勾选具体用例、全选或清空；不同执行器会按可支持的用例类型过滤已通过用例。
- 需求生成页支持直接上传接口文档（txt、md、csv、json、pdf）并生成测试用例；上传文档只作为本次生成上下文使用，不要求用户先进入知识库导入。
- 测试执行详情页支持对失败用例结果触发“LLM 归因”，归因结果会展示失败类型、置信度、根因、证据、修复建议、建议修复步骤 JSON 和是否建议沉淀知识；建议沉淀时可点击“沉淀知识”写入知识库；存在 `suggested_steps` 时可人工确认“应用到用例”，平台会写回关联测试用例并将状态改为待审核。
- 人工审核编辑页支持通过下拉框修改用例类型为 UI 自动化、接口/API、功能、回归、安全或人工；步骤编辑框支持 JSON 数组，便于保留 Playwright 的 selector、value、url、text 等字段。
- 人工审核页的已通过用例可直接单条执行；`web_ui` 用例自动使用 `playwright` 执行器，其他类型暂时使用 `mock`，提交后会切换到测试执行页并打开新运行详情。
- 人工审核页默认展示待审核用例，并支持按审核状态（待审核、已通过、已驳回、全部）和用例类型筛选，避免已处理用例混入待处理队列。
- 前端 API 客户端会把接口错误统一格式化为可定位的多行提示，包含请求方法、URL、HTTP 状态、后端 `detail`；网络失败或 CORS 拦截时会显示浏览器未收到响应及排查建议。
- 环境配置页支持录入项目环境变量 JSON；测试执行和单条执行 API 用例时会携带所选环境，执行器可通过 `${VARIABLE_NAME}` 引用这些变量。
- 知识库页：支持单条录入，也支持上传 txt、md、csv、json 批量导入需求、历史缺陷、业务规则和测试策略。

## 数据库

当前迁移版本：

```text
20260512_0007
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
- `test_run_artifacts.artifact_type`：附件类型，例如 `log`、`screenshot`、`evidence`、`video`、`trace`、`report`。
- `test_run_artifacts.path`：相对存储路径，不保存本机绝对路径。
- 本地执行产物目录约定为 `backend/storage/runs/{run_id}/`，该目录已加入 `.gitignore`。
- 附件可通过受保护接口 `/api/v1/runs/{run_id}/artifacts/{artifact_id}/download` 下载或预览，前端运行详情页会展示接口地址并通过当前 Bearer Token 拉取文件。

测试结果失败归因字段：

- `test_run_results.ai_diagnosis`：保存 LLM 或规则生成的结构化失败归因，包含 `failure_type`、`root_cause`、`evidence`、`fix_suggestions`、`suggested_steps`、`knowledge_type`、`should_save_knowledge`、`confidence` 和 `diagnosed_by`。
- 失败归因接口为 `POST /api/v1/runs/{run_id}/results/{result_id}/diagnose`，会写回当前测试结果并返回更新后的结果。
- 失败归因知识沉淀接口为 `POST /api/v1/runs/{run_id}/results/{result_id}/diagnosis-knowledge`，会将当前归因写入或更新为知识库条目，`source_id` 约定为 `run_result:{result_id}`。
- 需求生成链路会额外召回失败归因和选择器策略类知识，供 Agent 在生成 `web_ui` 步骤时补充 `selector_candidates`、规避已知失效 selector，并标记公开第三方站点的反自动化或 DOM 变更风险。

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
- Playwright 最小执行器已接入注册表，执行器名称为 `playwright`，支持 `web_ui` 用例的 `goto`、`click`、`fill`、`press`、`expect_text`、`expect_url` 受控动作，并支持候选 selector 兜底；失败时会生成截图和 `failure-evidence.json` 结构化证据附件。
- 前端测试执行页已可选择 `mock`、`playwright`、`api`、`pytest`、`command`、项目环境、headless 和 timeout，并在运行详情展示执行器、错误信息、附件路径、附件下载接口和查看按钮。
- API、pytest、command 三个执行器已完成最小接入和注册表验证；API 执行器用于 `api` 用例，pytest/command 执行器用于仓库测试或命令型测试的受控执行。
- 华测商城接口文档已用于验证项目 11 的 API 闭环：需求生成可产出“登录 -> 提取 token -> 加入购物车 -> 断言 code=0”的 `api` 用例；项目环境 `华测商城接口` 使用 `http://shop-xo.hctestedu.com/index.php`；本地执行 Run #12 / Result #15 通过。
- 接口文档驱动的通用 API 链路生成已完成首版验证：`ApiDocParser` 可从 `TestDocs/extracted_api_doc.txt` 提取登录和购物车接口，Agent 生成的 Case #75 使用 `${SHOPXO_USERNAME}` / `${SHOPXO_PASSWORD}` 环境变量登录、提取 `data.token` 后调用 `api/cart/save`；Run #13 / Result #16 通过。
- 需求生成页“需求 + 上传接口文档”链路已完成后端逻辑验证：使用 `TestDocs/extracted_api_doc.txt` 作为上传文档上下文时，无需先导入知识库即可生成登录后调用 `api/cart/save` 的 `api` 用例。
- “注册成功后正常登录”接口链路已修复并验证：当需求包含注册语义时，Agent 会生成 `api/user/reg -> api/user/login`，账号使用 `${SHOPXO_USERNAME}_${SHORT_TS}` 避免重复注册且满足用户名长度限制；Run #17 / Result #19 通过。
- 前端测试执行页已支持选择具体执行用例，提交运行时通过 `case_ids` 只执行被勾选的用例。
- 人工审核页已通过用例支持单条执行，并会自动打开新建运行的报告详情。
- 失败用例结果可触发 LLM 归因，已验证 Run #8 / Result #11 可由 DeepSeek 返回 `llm-diagnoser` 结构化诊断，并写入 `test_run_results.ai_diagnosis`；规则归因已验证可基于执行证据生成 `suggested_steps` 修复步骤建议，前端可将建议步骤应用回关联用例并转入待审核。Run #9 / Result #12 已验证 assertion mismatch 且日志存在 selector fallback 时，也能生成将 `#kw` 改为 `#chat-textarea` 并使用 `press Enter` 的修复步骤。
- 失败归因可人工沉淀到知识库，已验证 Run #8 / Result #11 可写入项目 11 的知识条目，类型为 `execution_failure`，标题前缀为“失败归因经验”。
- 项目 11 的百度搜索需求生成已验证可召回 `selector_strategy`、`execution_failure`、`anti_pattern` 和已审核用例经验；LLM 超时后规则兜底仍能生成 `web_ui` 用例和候选 selector。
- 需求“点击搜索框，搜索某关键词”已可由规则生成器产出 `web_ui` 用例和 Playwright 步骤；人工审核页可修改用例类型并保留结构化步骤
- DeepSeek/LLM 生成或自评审发生网络异常时，后端会自动回退到规则生成和规则评审，不再让前端只看到笼统的获取失败。
- 前端 API 错误详情展示构建验证通过，接口失败时会展示请求地址、HTTP 状态、后端错误详情或网络/CORS 排查建议。
- 人工审核页状态/类型筛选构建验证通过，默认只展示 `draft` 待审核用例
- Alembic head 已更新到 `20260512_0007`
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
- 使用百度这类公开第三方站点做 Playwright 验证时，可能遇到页面 DOM 变化、隐藏旧输入框、新版搜索入口需要特殊提交方式，以及 `wappass.baidu.com` 安全验证等反自动化拦截；平台应优先使用可控测试站点验证真实 UI 自动化闭环。

## 当前限制

当前仍然存在的限制：

- 测试执行已接入 Playwright、API、pytest 和 command 最小执行器，但 Playwright trace/视频采集、API 执行器更丰富的认证模式、跨用例数据共享和更完整的失败恢复能力仍待完善。
- 知识库当前是关键词/skill 召回，还不是向量检索
- 登录/权限系统仍是基础版本，还没有用户管理、角色分配、禁用账号和刷新 token
- 测试报告详情页已有附件查看/下载地址展示和失败归因入口，但还缺少视频、trace、归因审核流和更完整的执行过程可视化。
- CI 触发记录已可查询和展示，但还没有回写流水线状态或 PR 评论
- 项目环境变量已可注入执行器，但还缺少变量加密存储、敏感变量前端遮蔽和按环境复制/编辑能力。
- 文件上传当前支持文本类格式和 PDF 文本提取，但 Word 文档解析仍未接入；PDF 解析依赖运行环境安装 `pypdf`。
- 公开网站不适合作为稳定 UI 自动化基准，建议后续提供本地示例被测页面或演示站点，避免搜索引擎安全验证影响平台功能判断。

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
4. 将执行器包装为 Agent Tool，让测试 Agent 基于需求、代码变更、项目环境和历史知识自主规划测试范围、调用执行器、读取日志/截图/DOM 摘要并生成可审核修复建议。
5. 将审核通过的失败归因沉淀为 `selector_strategy`、`execution_failure`、`site_compatibility`、`anti_pattern` 等知识，供后续需求生成、用例修复和执行规划召回。

## 开发注意事项

- 代码注释和文档使用中文。
- 不要提交 `.env`、`.venv`、`node_modules`、`dist`。
- 后端新增表结构时使用 Alembic 迁移。
- DeepSeek 不可用时，Agent 应保留规则生成兜底。
- 前端功能应优先放入已有导航视图，不要再把所有功能堆到一个页面。
- 真实测试执行器接入前，不要移除当前模拟执行器；它是平台闭环的兜底验证能力。
