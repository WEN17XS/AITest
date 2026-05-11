from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Requirement, TestCase
from app.db.session import get_db
from app.schemas import GenerateCasesRequest, RequirementCreate, RequirementOut, TestCaseOut
from app.services.agent_service import TestCaseAgent
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


@router.post("", response_model=RequirementOut)
def create_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Requirement:
    requirement = Requirement(**payload.model_dump())
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[Requirement]:
    query = db.query(Requirement)
    if project_id:
        query = query.filter(Requirement.project_id == project_id)
    return query.order_by(Requirement.id.desc()).all()


@router.post("/generate-cases", response_model=list[TestCaseOut])
def generate_cases(
    payload: GenerateCasesRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[TestCase]:
    requirement_id = payload.requirement_id
    if payload.auto_save_requirement and requirement_id is None:
        requirement = Requirement(
            project_id=payload.project_id,
            title=payload.title,
            content=payload.content,
            source_type=payload.source_type,
        )
        db.add(requirement)
        db.commit()
        db.refresh(requirement)
        requirement_id = requirement.id

    knowledge_service = KnowledgeService()
    skill_chunks = knowledge_service.get_skill_context(db, payload.project_id, payload.content)
    skill_context = knowledge_service.format_skill_context(skill_chunks)
    generated = TestCaseAgent().generate_cases(payload.project_id, payload.content, requirement_id, skill_context)
    cases = []
    for item in generated:
        case = TestCase(**item.model_dump())
        db.add(case)
        cases.append(case)
    db.commit()
    for case in cases:
        db.refresh(case)
    return cases
