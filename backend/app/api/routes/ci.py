from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import CiTrigger, TestRun
from app.db.session import get_db
from app.schemas import CiTriggerOut, CiWebhookRequest, RunOut
from app.workers.tasks import execute_test_run

router = APIRouter()


@router.post("/webhook", response_model=RunOut)
def ci_webhook(
    payload: CiWebhookRequest,
    db: Session = Depends(get_db),
    x_aitesthub_token: str | None = Header(default=None),
) -> TestRun:
    if settings.webhook_secret and x_aitesthub_token != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Webhook token 无效")

    run = TestRun(
        project_id=payload.project_id,
        name=f"{payload.triggered_by} 触发测试",
        trigger_type=payload.triggered_by,
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        changed_files=payload.changed_files,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    trigger = CiTrigger(
        run_id=run.id,
        project_id=payload.project_id,
        provider=payload.triggered_by,
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        changed_files=payload.changed_files,
        payload=payload.model_dump(),
        status="accepted",
    )
    db.add(trigger)
    db.commit()
    db.refresh(run)
    execute_test_run.delay(run.id, None)
    return run


@router.get("/triggers", response_model=list[CiTriggerOut])
def list_ci_triggers(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[CiTrigger]:
    query = db.query(CiTrigger)
    if project_id:
        query = query.filter(CiTrigger.project_id == project_id)
    return query.order_by(CiTrigger.id.desc()).all()


@router.get("/triggers/{trigger_id}", response_model=CiTriggerOut)
def get_ci_trigger(trigger_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> CiTrigger:
    trigger = db.query(CiTrigger).options(selectinload(CiTrigger.run)).filter(CiTrigger.id == trigger_id).first()
    if trigger is None:
        raise HTTPException(status_code=404, detail="CI 触发记录不存在")
    return trigger
