from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import ProjectEnvironment, TestCase, TestRun, TestRunArtifact, TestRunResult
from app.services.executors import ExecutionContext, ExecutorRegistry, create_default_registry


class TestExecutionService:
    """测试执行服务。

    当前作为运行编排层：负责状态流转、用例选择、执行器分发和结果落库。
    具体执行逻辑由 services.executors 下的执行器实现。
    """

    def __init__(self, registry: ExecutorRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def run(self, db: Session, run_id: int, case_ids: list[int] | None = None) -> TestRun:
        run = db.get(TestRun, run_id)
        if run is None:
            raise ValueError(f"测试运行不存在: {run_id}")

        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.error_message = None
        db.commit()

        try:
            query = db.query(TestCase).filter(TestCase.project_id == run.project_id)
            if case_ids:
                query = query.filter(TestCase.id.in_(case_ids))
            else:
                query = query.filter(TestCase.status == "approved")
            cases = query.order_by(TestCase.priority.asc(), TestCase.id.asc()).all()

            environment = self._load_environment(db, run)
            variables = dict(environment.variables) if environment else {}
            if environment:
                variables["BASE_URL"] = environment.base_url

            context = ExecutionContext(
                run_id=run.id,
                project_id=run.project_id,
                run_name=run.name,
                trigger_type=run.trigger_type,
                cases=cases,
                branch=run.branch,
                commit_sha=run.commit_sha,
                changed_files=run.changed_files,
                environment=environment,
                variables=variables,
                artifacts_dir=self._prepare_artifacts_dir(run.id),
                config=run.executor_config,
            )
            executor = self.registry.resolve(cases, run.executor_type)
            execution_result = executor.execute(context)

            for case_result in execution_result.case_results:
                result = TestRunResult(
                    run_id=run.id,
                    case_id=case_result.case_id,
                    status=case_result.status,
                    duration_ms=case_result.duration_ms,
                    message=case_result.message,
                    logs=case_result.logs,
                    artifacts=case_result.artifacts,
                )
                db.add(result)
                db.flush()
                self._persist_case_artifacts(db, run.id, result.id, case_result.artifacts)

            run.status = execution_result.status
            run.summary = execution_result.summary
            run.report = execution_result.report
        except Exception as exc:
            run.status = "error"
            run.error_message = str(exc)
            run.summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 1}
            run.report = f"# 测试执行异常：{run.name}\n\n{exc}"

        run.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
        return run

    def _persist_case_artifacts(
        self,
        db: Session,
        run_id: int,
        result_id: int,
        artifact_paths: list[str],
    ) -> None:
        for path in artifact_paths:
            db.add(
                TestRunArtifact(
                    run_id=run_id,
                    result_id=result_id,
                    artifact_type=self._guess_artifact_type(path),
                    name=Path(path).name,
                    path=path,
                    content_type=self._guess_content_type(path),
                    size_bytes=self._artifact_size(run_id, path),
                    metadata_={},
                )
            )

    def _guess_artifact_type(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "screenshot"
        if suffix in {".webm", ".mp4"}:
            return "video"
        if suffix == ".zip":
            return "trace"
        if suffix in {".log", ".txt"}:
            return "log"
        return "artifact"

    def _guess_content_type(self, path: str) -> str | None:
        suffix = Path(path).suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".webm": "video/webm",
            ".mp4": "video/mp4",
            ".zip": "application/zip",
            ".log": "text/plain",
            ".txt": "text/plain",
        }.get(suffix)

    def _artifact_size(self, run_id: int, relative_path: str) -> int:
        artifact_path = self._run_artifacts_dir(run_id) / relative_path
        if not artifact_path.exists() or not artifact_path.is_file():
            return 0
        return artifact_path.stat().st_size

    def _prepare_artifacts_dir(self, run_id: int) -> Path:
        artifacts_dir = self._run_artifacts_dir(run_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        return artifacts_dir

    def _run_artifacts_dir(self, run_id: int) -> Path:
        return Path(__file__).resolve().parents[2] / "storage" / "runs" / str(run_id)

    def _load_environment(self, db: Session, run: TestRun) -> ProjectEnvironment | None:
        if run.environment_id is not None:
            environment = db.get(ProjectEnvironment, run.environment_id)
            if environment is None or environment.project_id != run.project_id:
                raise ValueError("测试运行指定的环境不存在或不属于当前项目")
            return environment

        return (
            db.query(ProjectEnvironment)
            .filter(ProjectEnvironment.project_id == run.project_id, ProjectEnvironment.is_default.is_(True))
            .order_by(ProjectEnvironment.id.asc())
            .first()
        )
