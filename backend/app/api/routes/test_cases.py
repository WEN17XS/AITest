from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_reviewer
from app.db.models import TestCase
from app.db.session import get_db
from app.schemas import TestCaseCreate, TestCaseOut, TestCaseReview, TestCaseUpdate
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


@router.post("", response_model=TestCaseOut)
def create_test_case(payload: TestCaseCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> TestCase:
    case = TestCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[TestCaseOut])
def list_test_cases(
    project_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[TestCase]:
    query = db.query(TestCase)
    if project_id:
        query = query.filter(TestCase.project_id == project_id)
    if status:
        query = query.filter(TestCase.status == status)
    return query.order_by(TestCase.id.desc()).all()


@router.patch("/{case_id}", response_model=TestCaseOut)
def update_test_case(
    case_id: int,
    payload: TestCaseUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> TestCase:
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="测试用例不存在")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in {"draft", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="状态只能是 draft、approved 或 rejected")
    for key, value in data.items():
        setattr(case, key, value)

    db.commit()
    db.refresh(case)
    return case


@router.patch("/{case_id}/review", response_model=TestCaseOut)
def review_test_case(
    case_id: int,
    payload: TestCaseReview,
    db: Session = Depends(get_db),
    _user=Depends(require_reviewer),
) -> TestCase:
    if payload.status not in {"draft", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="状态只能是 draft、approved 或 rejected")

    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    case.status = payload.status
    case.review_comment = payload.review_comment
    db.commit()
    db.refresh(case)
    knowledge_service = KnowledgeService()
    if case.status == "approved":
        source_type = "approved_test_case" if case.generated_by == "human" else "reviewed_test_case"
        knowledge_service.create_from_test_case(db, case, source_type=source_type, status="verified")
    elif case.status == "rejected":
        knowledge_service.create_rejection_pattern(db, case, payload.review_comment)
    return case
