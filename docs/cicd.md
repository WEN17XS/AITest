# CI/CD 接入说明

AITestHub 提供 webhook 入口给 Jenkins、GitHub Actions、GitLab CI 或其他流水线系统调用。

## Webhook 地址

```text
POST http://你的服务地址/api/v1/ci/webhook
```

请求头：

```text
X-AITestHub-Token: .env 中配置的 WEBHOOK_SECRET
```

请求体：

```json
{
  "project_id": 1,
  "branch": "main",
  "commit_sha": "abc123",
  "changed_files": ["backend/app/main.py"],
  "triggered_by": "jenkins"
}
```

Webhook 成功后会创建一条测试运行记录和一条 CI 触发记录。登录前端后，可以在“测试执行”页面查看：

- 测试运行详情
- 测试报告正文
- 每条用例结果和日志
- 关联 CI 触发来源、分支、提交号、变更文件数量和原始 payload

也可以通过接口查询：

```http
GET /api/v1/ci/triggers?project_id=1
GET /api/v1/ci/triggers/{trigger_id}
GET /api/v1/runs/{run_id}
```

## Jenkins 示例

```groovy
pipeline {
  agent any
  stages {
    stage('AITestHub') {
      steps {
        sh '''
          curl -X POST http://localhost:8000/api/v1/ci/webhook \
            -H "Content-Type: application/json" \
            -H "X-AITestHub-Token: change-me" \
            -d '{
              "project_id": 1,
              "branch": "'$BRANCH_NAME'",
              "commit_sha": "'$GIT_COMMIT'",
              "changed_files": [],
              "triggered_by": "jenkins"
            }'
        '''
      }
    }
  }
}
```

## GitHub Actions 示例

```yaml
name: AITestHub

on:
  push:
    branches: [main]
  pull_request:

jobs:
  aitesthub:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Trigger AITestHub
        run: |
          curl -X POST "${{ secrets.AITESTHUB_URL }}/api/v1/ci/webhook" \
            -H "Content-Type: application/json" \
            -H "X-AITestHub-Token: ${{ secrets.AITESTHUB_TOKEN }}" \
            -d '{
              "project_id": 1,
              "branch": "${{ github.ref_name }}",
              "commit_sha": "${{ github.sha }}",
              "changed_files": [],
              "triggered_by": "github-actions"
            }'
```

## 后续增强方向

- 从 CI 中传入 git diff 文件列表
- 根据变更文件选择测试用例
- 将报告回写到 PR 评论
- 将失败结果作为流水线质量门禁
