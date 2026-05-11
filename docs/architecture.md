# 架构设计

## 目标

AITestHub 的目标是给未来项目提供统一测试入口：

- Agent 根据需求、代码变更和知识库生成测试用例
- 人工审核决定哪些用例进入正式测试资产
- 测试执行器负责触发 UI、API、单元、集成、回归等测试
- CI/CD 通过 webhook 接入，自动获得质量门禁结果
- 向量知识库存储历史需求、缺陷、用例、失败原因和项目文档

## 模块说明

### 前端

前端位于 `frontend/`，提供：

- 项目管理
- 需求输入
- Agent 用例生成
- 人工审核
- 测试执行
- 报告查看

### 后端 API

后端位于 `backend/app/`，核心模块：

- `api/routes/projects.py`：项目管理
- `api/routes/requirements.py`：需求录入和用例生成
- `api/routes/test_cases.py`：测试用例和审核
- `api/routes/runs.py`：测试任务
- `api/routes/ci.py`：CI/CD webhook
- `api/routes/knowledge.py`：知识库

### Agent 编排层

当前入口是 `backend/app/services/agent_service.py`。

第一阶段已经接入 `langchain-deepseek`，通过 `ChatDeepSeek` 调用 DeepSeek 生成结构化测试用例。没有密钥、模型不可用或返回格式异常时，会回退到规则生成器，保证平台闭环可用。

当前相关文件：

- `backend/app/services/llm_service.py`：DeepSeek 模型初始化
- `backend/app/services/agent_service.py`：测试用例生成 Agent
- `backend/app/api/routes/llm.py`：大模型健康检查

后续可以扩展：

- 需求拆解 Agent
- 用例设计 Agent
- 代码变更影响分析 Agent
- 失败归因 Agent
- 报告生成 Agent

### 测试执行层

当前入口是 `backend/app/services/execution_service.py`。

第一版使用模拟执行器。后续可以按用例类型分发到：

- Playwright：Web UI 自动化
- pytest：Python/API/集成测试
- Newman：Postman 集合
- JMeter 或 Locust：性能测试
- 自定义脚本执行器

第二阶段执行器架构设计见 `docs/executor-architecture.md`。目标分层为：

```text
API / CI 入口
  -> 运行编排层 TestExecutionService
  -> 执行器注册表 ExecutorRegistry
  -> 具体执行器 TestExecutor
  -> 结果与附件持久化
```

关键约定：

- `TestExecutionService` 只负责运行编排、状态更新、结果落库和报告聚合，不直接包含 Playwright 或 pytest 细节。
- 具体执行器实现统一的 `TestExecutor` 接口，返回标准化 `ExecutionResult`。
- 当前模拟执行器后续迁移为 `MockExecutor`，继续作为平台闭环兜底能力。
- 第二阶段建议新增运行级执行器配置、环境引用和附件模型，用于承载截图、视频、trace、日志等真实执行产物。

### 数据库

使用 PostgreSQL 存储业务数据，使用 pgvector 预留向量字段。

主要表：

- `projects`
- `requirements`
- `test_cases`
- `test_runs`
- `test_run_results`
- `knowledge_chunks`

### 中间件

Redis 用于 Celery broker 和 result backend。

测试执行默认异步提交，避免前端等待长时间任务。

## 后续建议

第一版重点跑通闭环。第二版建议优先做：

- 接入真实 LLM
- 接入 Playwright
- 接入 pytest
- 增加 git diff 影响分析
- 增加用例覆盖率矩阵
- 增加报告导出
