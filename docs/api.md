# API 说明

后端启动后可以访问自动生成的接口文档：

```text
http://localhost:8000/docs
```

除 `POST /api/v1/auth/register`、`POST /api/v1/auth/login` 和 `POST /api/v1/ci/webhook` 外，当前业务接口都需要携带登录 token：

```http
Authorization: Bearer <access_token>
```

## 登录与权限

注册账号：

```http
POST /api/v1/auth/register
```

```json
{
  "username": "admin_001",
  "display_name": "平台管理员",
  "password": "Admin12345"
}
```

账号规则：

- 账号只能包含英文字母、数字、下划线，长度 4-32 位。
- 显示名称长度 2-30 位。
- 密码长度 8-64 位，不能包含空白字符，并且必须同时包含字母和数字。

第一个注册用户会自动成为 `admin`，后续注册用户默认为 `tester`。

登录账号：

```http
POST /api/v1/auth/login
```

```json
{
  "username": "admin_001",
  "password": "Admin12345"
}
```

获取当前用户：

```http
GET /api/v1/auth/me
```

角色说明：

- `admin`：拥有审核权限和项目删除权限。
- `reviewer`：拥有审核权限。
- `tester`：可以创建、编辑和执行测试，但不能通过或驳回测试用例。

## 项目

创建项目：

```http
POST /api/v1/projects
```

```json
{
  "name": "示例项目",
  "description": "用于测试的平台接入项目",
  "repo_url": "https://example.com/repo.git",
  "default_branch": "main"
}
```

删除项目：

```http
DELETE /api/v1/projects/{project_id}
```

只有 `admin` 可以删除项目。删除项目会级联删除该项目下的需求、测试用例、运行记录、环境配置、知识条目和 CI 触发记录。

## 需求与用例生成

根据自然语言或需求文档内容生成测试用例：

```http
POST /api/v1/requirements/generate-cases
```

```json
{
  "project_id": 1,
  "title": "登录需求",
  "content": "用户可以使用账号密码登录系统，登录失败时需要提示错误原因。",
  "source_type": "text",
  "auto_save_requirement": true
}
```

生成的用例默认是 `draft`，需要人工审核。
生成前会读取项目知识库中的 `active` / `verified` skill 知识作为上下文。生成后会执行 AI 自评审，并在每条用例的 `ai_review` 字段中返回风险等级、分数、遗漏、矛盾、越界、重复和建议。

## 人工审核

```http
PATCH /api/v1/test-cases/{case_id}/review
```

```json
{
  "status": "approved",
  "review_comment": "人工审核通过"
}
```

状态说明：

- `draft`：待审核
- `approved`：已通过
- `rejected`：已驳回

审核后的知识闭环：

- 审核通过的用例会自动沉淀到知识库，`source_type` 为 `approved_test_case` 或 `reviewed_test_case`。
- 驳回的用例会自动沉淀为 `anti_pattern`，用于提示后续 Agent 避免类似问题。
- 人工修改后再审核通过的用例会以最终版本沉淀为正向 skill 知识。

## 测试执行

```http
POST /api/v1/runs
```

```json
{
  "project_id": 1,
  "name": "手动回归测试",
  "case_ids": [1, 2, 3],
  "trigger_type": "manual"
}
```

如果不传 `case_ids`，默认执行该项目下所有已审核通过的用例。

查看测试报告详情：

```http
GET /api/v1/runs/{run_id}
```

详情会返回运行基础信息、执行结果列表、报告正文，以及关联的 `ci_trigger`。

## CI 触发记录

查询 CI 触发记录：

```http
GET /api/v1/ci/triggers?project_id=1
```

查看单条 CI 触发记录：

```http
GET /api/v1/ci/triggers/{trigger_id}
```

CI webhook 本身不使用用户 token，而是使用 `X-AITestHub-Token` 校验：

```http
POST /api/v1/ci/webhook
X-AITestHub-Token: <WEBHOOK_SECRET>
```

## 知识库

```http
POST /api/v1/knowledge
```

```json
{
  "project_id": 1,
  "source_type": "historical_defect",
  "source_id": "REQ-001",
  "title": "登录模块历史缺陷",
  "content": "登录失败时曾错误写入会话，生成用例时必须覆盖错误密码、空密码、锁定账号和会话不应创建。",
  "status": "active",
  "skill_name": "登录缺陷测试 skill",
  "triggers": ["登录", "会话", "错误密码"],
  "quality_score": 5,
  "metadata_": {
    "module": "auth"
  }
}
```

知识字段说明：

- `source_type`：建议使用 `requirement`、`historical_defect`、`business_rule`、`test_strategy`、`approved_test_case`、`reviewed_test_case`、`anti_pattern`。
- `status`：建议使用 `candidate`、`active`、`verified`、`rejected`。
- `skill_name`：知识所属的测试 skill 名称。
- `triggers`：触发该 skill 的关键词。
- `quality_score`：1-5 分，生成时优先召回高分知识。

当前仍是关键词召回，后续接入 embedding 模型后会升级为向量检索。

### 批量导入知识

```http
POST /api/v1/knowledge/import
Content-Type: multipart/form-data
```

表单字段：

- `project_id`：项目 ID。
- `source_type`：知识来源类型，建议使用 `requirement`、`historical_defect`、`business_rule`、`test_strategy`。
- `status`：默认 `active`。
- `skill_name`：导入后归属的测试 skill 名称。
- `quality_score`：1-5 分，默认 3。
- `file`：上传文件。

支持格式：

- `.md`：按 Markdown 标题切分为多条知识。
- `.txt`：按空行和长度切分为多条知识。
- `.csv`：第一行作为表头，推荐字段为 `title`、`content`、`source_type`、`source_id`、`skill_name`、`triggers`、`quality_score`。
- `.json`：支持单个对象、对象数组，或 `{ "items": [...] }`。

返回示例：

```json
{
  "imported": 2,
  "skipped": 0,
  "items": []
}
```
