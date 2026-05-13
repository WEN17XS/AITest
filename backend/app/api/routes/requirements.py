from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Requirement, TestCase
from app.db.session import get_db
from app.schemas import GenerateCasesRequest, RequirementCreate, RequirementOut, TestCaseOut
from app.services.agent_service import TestCaseAgent
from app.services.document_text_service import DocumentTextService
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
    skill_chunks = knowledge_service.get_generation_context(db, payload.project_id, payload.content)
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


@router.post("/generate-cases-with-doc", response_model=list[TestCaseOut])
async def generate_cases_with_doc(
    project_id: int = Form(...),
    title: str = Form("接口文档需求"),
    content: str = Form(...),
    source_type: str = Form("text"),
    auto_save_requirement: bool = Form(True),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[TestCase]:
    requirement_id = None
    if auto_save_requirement:
        requirement = Requirement(
            project_id=project_id,
            title=title,
            content=content,
            source_type=source_type,
        )
        db.add(requirement)
        db.commit()
        db.refresh(requirement)
        requirement_id = requirement.id

    knowledge_service = KnowledgeService()
    skill_chunks = knowledge_service.get_generation_context(db, project_id, content)
    skill_context_parts = [knowledge_service.format_skill_context(skill_chunks)]

    if file is not None and file.filename:
        raw = await file.read()
        if raw:
            if len(raw) > 8 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="接口文档不能超过 8MB")
            try:
                document_text = DocumentTextService().extract_text(file.filename, raw)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            skill_context_parts.append(f"上传接口文档：{file.filename}\n{document_text[:120000]}")

    skill_context = "\n\n".join(part for part in skill_context_parts if part.strip())
    generated = TestCaseAgent().generate_cases(project_id, content, requirement_id, skill_context)
    cases = []
    for item in generated:
        case = TestCase(**item.model_dump())
        db.add(case)
        cases.append(case)
    db.commit()
    for case in cases:
        db.refresh(case)
    return cases
