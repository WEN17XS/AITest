from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.models import TestRun, TestRunArtifact, TestRunResult
from app.db.session import get_db
from app.schemas import KnowledgeOut, RunCreate, RunDetailOut, RunOut, RunResultOut
from app.services.executors import create_default_registry
from app.services.failure_diagnosis_service import FailureDiagnosisService
from app.workers.tasks import execute_test_run

router = APIRouter()


@router.post("", response_model=RunOut)
def create_run(payload: RunCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> TestRun:
    try:
        create_default_registry().get(payload.executor_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{exc}。请确认后端和 Celery Worker 已重启到最新代码。")

    run = TestRun(
        project_id=payload.project_id,
        environment_id=payload.environment_id,
        name=payload.name,
        trigger_type=payload.trigger_type,
        executor_type=payload.executor_type,
        executor_config=payload.executor_config,
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        changed_files=payload.changed_files,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    execute_test_run.delay(run.id, payload.case_ids)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[TestRun]:
    query = db.query(TestRun).options(selectinload(TestRun.results))
    if project_id:
        query = query.filter(TestRun.project_id == project_id)
    return query.order_by(TestRun.id.desc()).all()


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> TestRun:
    run = (
        db.query(TestRun)
        .options(selectinload(TestRun.results), selectinload(TestRun.ci_trigger), selectinload(TestRun.artifacts))
        .filter(TestRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="测试运行不存在")
    return run


@router.post("/{run_id}/results/{result_id}/diagnose", response_model=RunResultOut)
def diagnose_run_result(
    run_id: int,
    result_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> TestRunResult:
    result = (
        db.query(TestRunResult)
        .filter(TestRunResult.id == result_id, TestRunResult.run_id == run_id)
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="测试结果不存在")
    return FailureDiagnosisService().diagnose_result(db, result_id)


@router.post("/{run_id}/results/{result_id}/diagnosis-knowledge", response_model=KnowledgeOut)
def save_run_result_diagnosis_knowledge(
    run_id: int,
    result_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = (
        db.query(TestRunResult)
        .filter(TestRunResult.id == result_id, TestRunResult.run_id == run_id)
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="测试结果不存在")
    try:
        return FailureDiagnosisService().save_diagnosis_knowledge(db, result_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{run_id}/artifacts/{artifact_id}/download")
def download_artifact(
    run_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> FileResponse:
    artifact = (
        db.query(TestRunArtifact)
        .filter(TestRunArtifact.id == artifact_id, TestRunArtifact.run_id == run_id)
        .first()
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="测试运行附件不存在")

    run_dir = _run_artifacts_dir(run_id)
    artifact_path = (run_dir / artifact.path).resolve()
    try:
        artifact_path.relative_to(run_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="附件路径非法")

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"附件文件不存在：{artifact.path}")

    return FileResponse(
        artifact_path,
        media_type=artifact.content_type or "application/octet-stream",
        filename=artifact.name,
    )


def _run_artifacts_dir(run_id: int) -> Path:
    return (Path(__file__).resolve().parents[3] / "storage" / "runs" / str(run_id)).resolve()
