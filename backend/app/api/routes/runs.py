from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.models import TestRun
from app.db.session import get_db
from app.schemas import RunCreate, RunDetailOut, RunOut
from app.workers.tasks import execute_test_run

router = APIRouter()


@router.post("", response_model=RunOut)
def create_run(payload: RunCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> TestRun:
    run = TestRun(
        project_id=payload.project_id,
        name=payload.name,
        trigger_type=payload.trigger_type,
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
        .options(selectinload(TestRun.results), selectinload(TestRun.ci_trigger))
        .filter(TestRun.id == run_id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="测试运行不存在")
    return run
