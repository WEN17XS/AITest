# 路线图

## 第一阶段：平台闭环

- 项目管理
- 需求输入
- langchain-deepseek Agent 生成测试用例
- 人工审核和编辑测试用例
- 手动触发测试
- CI webhook 触发测试
- 测试报告展示
- PostgreSQL + pgvector 表结构
- 项目环境配置
- 知识库录入和关键词查询

## 第二阶段：真实测试执行

目标是把当前模拟执行闭环升级为可插拔真实执行体系。实施批次如下：

1. 执行器基础架构
   - 抽出 `TestExecutor` 基础接口、执行上下文和标准结果对象。
   - 增加 `ExecutorRegistry`，统一按执行器类型或用例类型选择执行器。
   - 将现有模拟执行逻辑迁移为 `MockExecutor`，保持当前行为兼容。

2. 运行配置和环境注入
   - 给测试运行增加 `executor_type`、`environment_id`、`executor_config`、`error_message`。
   - 编排层加载项目默认环境或指定环境。
   - 将 `base_url` 和安全变量注入执行上下文。

3. 附件和执行产物
   - 新增 `test_run_artifacts`。
   - 定义本地存储目录 `backend/storage/runs/{run_id}/`。
   - 支持运行级和用例级日志、截图、视频、trace、结构化报告。

4. Playwright Web UI 执行器
   - 支持 `web_ui` 用例类型。
   - 第一版支持 `goto`、`click`、`fill`、`expect_text`、`expect_url` 等受控动作。
   - 失败时保存截图和 trace，并写入运行详情。

5. pytest/API 执行器
   - 支持 `api` 和 `integration` 用例类型。
   - 支持环境变量注入、pytest 执行、结果解析和日志收集。
   - 后续扩展关联仓库内已有 pytest 标记。

6. 稳定性和智能化
   - 失败用例重跑。
   - flaky 用例识别。
   - 失败归因 Agent。
   - CI 状态回写和质量门禁。

## 第三阶段：智能测试

- 接入 LLM
- 知识库向量检索
- 根据 git diff 推荐测试范围
- 需求覆盖率矩阵
- 缺陷相似度召回
- 自动失败归因

## 第四阶段：组织级能力

- 用户和权限
- 审核流配置
- 多环境管理
- 测试数据管理
- 项目模板
- 报告导出和消息通知
