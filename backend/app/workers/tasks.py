from app.db.session import SessionLocal
from app.services.execution_service import TestExecutionService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.execute_test_run")
def execute_test_run(run_id: int, case_ids: list[int] | None = None) -> dict[str, int | str]:
    db = SessionLocal()
    try:
        run = TestExecutionService().run(db, run_id, case_ids)
        return {"run_id": run.id, "status": run.status}
    finally:
        db.close()

