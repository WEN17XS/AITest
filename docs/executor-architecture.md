# 测试执行器架构设计

## 设计目标

第二阶段的核心目标是把当前模拟执行器升级为可插拔真实执行体系，同时保留模拟执行器作为平台闭环兜底能力。

执行器架构需要满足：

- 支持手动触发和 CI webhook 触发共用同一执行链路。
- 支持按项目、环境、分支、提交和用例集合创建测试运行。
- 支持多个执行器并存，例如 `mock`、`playwright`、`pytest`。
- 执行器只关心如何执行测试，运行状态、结果落库、报告聚合由编排层统一处理。
- 执行过程可以产生日志、截图、视频、trace、JUnit XML、pytest JSON 等附件。
- 真实执行失败时不破坏平台闭环，必要时可以回退到模拟执行器或标记为 `error`。

## 当前执行链路

当前链路如下：

```text
POST /api/v1/runs
  -> 创建 test_runs，状态 queued
  -> Celery execute_test_run(run_id, case_ids)
  -> TestExecutionService.run()
  -> 查询已审核或指定测试用例
  -> 模拟生成 test_run_results
  -> 聚合 summary、report、status
```

CI webhook 链路与手动运行类似，只是在创建 `test_runs` 前会先校验 `X-AITestHub-Token`，并额外写入 `ci_triggers`。

## 分层设计

目标执行层拆成四层：

```text
API / CI 入口
  -> 运行编排层 TestExecutionService
  -> 执行器注册表 ExecutorRegistry
  -> 具体执行器 TestExecutor
  -> 结果与附件持久化
```

### API / CI 入口

职责：

- 接收运行请求。
- 创建 `test_runs`。
- 将 `run_id` 和可选 `case_ids` 投递给 Celery。
- 不直接执行测试，也不关心具体执行器实现。

后续 `RunCreate` 建议新增字段：

- `executor_type`：可选，指定本次运行使用的执行器，例如 `mock`、`playwright`、`pytest`。为空时由编排层按用例类型和项目配置决定。
- `environment_id`：可选，指定项目环境配置。为空时使用项目默认环境。
- `executor_config`：可选，保存本次运行级配置，例如浏览器类型、超时时间、是否录制视频。

### 运行编排层

建议继续由 `backend/app/services/execution_service.py` 承担入口职责，但内部只做编排，不直接实现具体执行逻辑。

职责：

- 校验 `TestRun` 是否存在。
- 标记运行状态为 `running`，记录 `started_at`。
- 选择测试用例。
- 加载项目、环境变量、分支、提交、变更文件等上下文。
- 根据 `executor_type` 或用例类型选择执行器。
- 调用执行器并接收标准化结果。
- 统一写入 `test_run_results`、附件记录、`summary` 和 `report`。
- 捕获未处理异常，将运行标记为 `error`，保留错误日志。

编排层不应该包含 Playwright、pytest 等框架细节。

### 执行器注册表

新增建议模块：

```text
backend/app/services/executors/
  __init__.py
  base.py
  registry.py
  mock_executor.py
  playwright_executor.py
  pytest_executor.py
```

`ExecutorRegistry` 负责：

- 注册执行器名称和实例。
- 按显式 `executor_type` 查找执行器。
- 在未指定执行器时，根据用例类型选择默认执行器。
- 对不支持的类型给出明确错误。

推荐默认映射：

```text
manual      -> mock
web_ui      -> playwright
api         -> pytest
integration -> pytest
```

在真实执行器未实现前，`web_ui` 和 `api` 可以先回退到 `mock`，但需要在报告中说明当前仍为回退执行。

### 执行器接口

所有执行器实现同一个最小接口：

```python
class TestExecutor(Protocol):
    name: str
    supported_case_types: set[str]

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        ...
```

核心数据对象建议放在 `base.py`：

- `ExecutionContext`
  - `run_id`
  - `project_id`
  - `environment`
  - `cases`
  - `branch`
  - `commit_sha`
  - `changed_files`
  - `variables`
  - `workspace_dir`
  - `artifacts_dir`
  - `config`

- `CaseExecutionResult`
  - `case_id`
  - `status`
  - `duration_ms`
  - `message`
  - `logs`
  - `artifacts`
  - `metadata`

- `ExecutionResult`
  - `status`
  - `case_results`
  - `summary`
  - `report`
  - `logs`
  - `artifacts`

接口先支持批量执行。后续如果某些执行器更适合逐用例执行，可以在执行器内部拆分，不影响编排层。

## 执行器类型

### mock

现有模拟执行器迁移为 `MockExecutor`。

职责：

- 保留当前闭环验证能力。
- 不依赖浏览器、测试仓库或外部命令。
- 适合演示、兜底和平台功能回归。

### playwright

用于 Web UI 自动化。

职责：

- 使用项目环境的 `base_url` 和 `variables` 注入测试上下文。
- 支持 Chromium 起步，后续扩展 Firefox、WebKit。
- 保存截图、视频、trace 和浏览器控制台日志。
- 将失败定位信息写入 `message` 和 `logs`。

建议输入约定：

- `TestCase.type = "web_ui"`。
- `steps` 继续保存结构化步骤，后续由执行器翻译为 Playwright 动作，或由 Agent 生成 Playwright 脚本引用。
- 第一版可以先支持受控动作集，例如 `goto`、`click`、`fill`、`expect_text`、`expect_url`。

当前最小执行器已接入：

- 执行器名称：`playwright`
- 用例类型：`web_ui`
- 支持动作：`goto`、`click`、`fill`、`expect_text`、`expect_url`
- 默认配置：`browser=chromium`、`headless=true`、`timeout_ms=10000`、`screenshot_on_failure=true`
- 失败截图会写入 `backend/storage/runs/{run_id}/cases/{case_id}/failure.png`，并登记到 `test_run_artifacts`。
- 运行前需要安装 Python 依赖并执行 `playwright install chromium`。

### pytest

用于 API、Python 集成测试或仓库内已有 pytest 用例。

职责：

- 在受控工作目录中执行 pytest。
- 支持环境变量注入。
- 解析 pytest 输出、JUnit XML 或 JSON report。
- 将用例结果映射回 `test_run_results`。

建议输入约定：

- `TestCase.type = "api"` 或 `integration`。
- `steps` 可以描述请求、断言和数据准备。
- 第一版可以先支持平台生成的轻量 API 测试文件，后续再支持关联仓库内已有 pytest 标记。

## 状态模型

`test_runs.status` 建议统一使用：

- `queued`：已创建，等待执行。
- `running`：执行中。
- `passed`：所有可执行结果通过。
- `failed`：存在失败用例。
- `skipped`：没有可执行用例，或被规则跳过。
- `error`：执行器初始化、环境准备或系统异常。
- `canceled`：用户或系统取消。

`test_run_results.status` 建议统一使用：

- `passed`
- `failed`
- `skipped`
- `error`

区别：

- `failed` 表示测试断言失败或业务行为不符合预期。
- `error` 表示执行器、环境、依赖、脚本或平台异常。

## 附件模型

当前 `test_run_results.artifacts` 是字符串列表，适合第一阶段展示，但无法表达附件类型、大小、归属和元数据。

第二阶段已新增 `test_run_artifacts` 表：

```text
id
run_id
result_id
artifact_type
name
path
content_type
size_bytes
metadata
created_at
```

约定：

- `run_id` 必填。
- `result_id` 可空，运行级日志、汇总报告、完整 trace 可以不绑定单个用例。
- `path` 存相对存储路径，不存本机绝对路径。
- 第一版附件仍落本地目录，后续可以切换到对象存储。

建议本地目录：

```text
backend/storage/runs/{run_id}/
  run.log
  cases/{case_id}/
    screenshot.png
    video.webm
    trace.zip
```

为了兼容当前前端，编排层可以继续把主要附件路径同步写入 `test_run_results.artifacts`。
当前编排层已为每次运行准备 `artifacts_dir`，真实执行器接入时直接写入该目录并创建附件记录即可。

## 环境变量与密钥

执行上下文中的变量来源：

1. 项目环境 `project_environments.variables`
2. 项目环境 `base_url`
3. 运行级 `executor_config`
4. CI payload 中允许透传的安全字段

约定：

- 日志和报告中必须脱敏疑似密钥字段，例如 `token`、`secret`、`password`、`key`。
- 不把 `.env` 原文写入日志或附件。
- 执行器只能接收编排层筛选后的变量。

## 报告聚合

执行器返回机器可读结果，编排层生成平台报告。

报告建议包含：

- 执行器名称和版本。
- 触发方式、分支、提交。
- 环境名称和 `base_url`。
- 通过、失败、跳过、错误数量。
- 失败用例摘要。
- 附件索引。
- 后续失败归因 Agent 的占位字段。

## 数据库迁移建议

第二阶段第一批迁移建议：

- `test_runs.executor_type`
- `test_runs.environment_id`
- `test_runs.executor_config`
- `test_runs.error_message`
- `test_run_results.metadata`
- 新增 `test_run_artifacts`

为了减少前端改动，已有字段继续保留：

- `test_runs.summary`
- `test_runs.report`
- `test_run_results.logs`
- `test_run_results.artifacts`

## 实施顺序

建议按以下顺序落地：

1. 抽出 `executors/base.py`、`registry.py`、`mock_executor.py`，保持现有功能不变。
2. 给 `test_runs` 增加执行器、环境和配置字段。
3. 编排层接入注册表，默认仍使用 `mock`。
4. 新增附件模型和本地存储目录约定。
5. 接入 Playwright 最小执行器。
6. 接入 pytest/API 最小执行器。
7. 增加失败重跑、flaky 识别和失败归因 Agent。

## 设计边界

本设计阶段只定义执行器扩展边界，不立即替换现有模拟执行行为。下一步实现时应确保：

- 当前 `POST /api/v1/runs` 行为保持兼容。
- 当前测试执行页仍能展示已有运行结果。
- 真实执行器接入失败时，错误可以在运行详情中被看见。
- 模拟执行器不能被删除。
