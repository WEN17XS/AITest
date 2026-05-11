import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,32}$")


class UserRegister(BaseModel):
    username: str
    password: str
    display_name: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()
        if not USERNAME_PATTERN.fullmatch(username):
            raise ValueError("账号只能包含英文字母、数字、下划线，长度 4-32 位")
        return username

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        display_name = value.strip()
        if not 2 <= len(display_name) <= 30:
            raise ValueError("显示名称长度必须为 2-30 位")
        return display_name

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not 8 <= len(value) <= 64:
            raise ValueError("密码长度必须为 8-64 位")
        if any(ch.isspace() for ch in value):
            raise ValueError("密码不能包含空白字符")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("密码必须同时包含字母和数字")
        return value


class UserLogin(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    repo_url: str | None = None
    default_branch: str = "main"


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectEnvironmentCreate(BaseModel):
    project_id: int
    name: str
    base_url: str
    variables: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class ProjectEnvironmentOut(ProjectEnvironmentCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequirementCreate(BaseModel):
    project_id: int
    title: str
    content: str
    source_type: str = "text"


class RequirementOut(RequirementCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerateCasesRequest(BaseModel):
    project_id: int
    requirement_id: int | None = None
    title: str = "自然语言需求"
    content: str
    source_type: str = "text"
    auto_save_requirement: bool = True


class TestCaseCreate(BaseModel):
    project_id: int
    requirement_id: int | None = None
    title: str
    type: str = "manual"
    priority: str = "P2"
    status: str = "draft"
    preconditions: str | None = None
    steps: list[dict[str, Any]]
    expected_result: str
    tags: list[str] = Field(default_factory=list)
    generated_by: str = "human"
    ai_review: dict[str, Any] = Field(default_factory=dict)


class TestCaseUpdate(BaseModel):
    title: str | None = None
    type: str | None = None
    priority: str | None = None
    status: str | None = None
    preconditions: str | None = None
    steps: list[dict[str, Any]] | None = None
    expected_result: str | None = None
    tags: list[str] | None = None
    review_comment: str | None = None
    ai_review: dict[str, Any] | None = None


class TestCaseReview(BaseModel):
    status: str
    review_comment: str | None = None


class TestCaseOut(TestCaseCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunCreate(BaseModel):
    project_id: int
    environment_id: int | None = None
    name: str = "手动测试执行"
    case_ids: list[int] | None = None
    trigger_type: str = "manual"
    executor_type: str = "mock"
    executor_config: dict[str, Any] = Field(default_factory=dict)
    branch: str | None = None
    commit_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list)


class RunResultOut(BaseModel):
    id: int
    case_id: int | None
    status: str
    duration_ms: int
    message: str | None
    logs: str | None
    artifacts: list[str]

    model_config = ConfigDict(from_attributes=True)


class RunArtifactOut(BaseModel):
    id: int
    run_id: int
    result_id: int | None
    artifact_type: str
    name: str
    path: str
    content_type: str | None
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CiTriggerOut(BaseModel):
    id: int
    run_id: int
    project_id: int
    provider: str
    branch: str | None
    commit_sha: str | None
    changed_files: list[str]
    payload: dict[str, Any]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunOut(BaseModel):
    id: int
    project_id: int
    environment_id: int | None
    name: str
    trigger_type: str
    executor_type: str
    executor_config: dict[str, Any]
    status: str
    branch: str | None
    commit_sha: str | None
    changed_files: list[str]
    summary: dict[str, Any]
    report: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    results: list[RunResultOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RunDetailOut(RunOut):
    ci_trigger: CiTriggerOut | None = None
    artifacts: list[RunArtifactOut] = Field(default_factory=list)


class CiWebhookRequest(BaseModel):
    project_id: int
    environment_id: int | None = None
    executor_type: str = "mock"
    executor_config: dict[str, Any] = Field(default_factory=dict)
    branch: str | None = None
    commit_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    triggered_by: str = "ci"


class KnowledgeCreate(BaseModel):
    project_id: int
    source_type: str
    source_id: str | None = None
    title: str
    content: str
    status: str = "active"
    skill_name: str | None = None
    triggers: list[str] = Field(default_factory=list)
    quality_score: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeOut(KnowledgeCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSearchRequest(BaseModel):
    project_id: int
    query: str
    limit: int = 5


class KnowledgeImportOut(BaseModel):
    imported: int
    skipped: int
    items: list[KnowledgeOut]


class SkillKnowledgeOut(KnowledgeOut):
    pass
