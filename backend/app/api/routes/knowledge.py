from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import KnowledgeChunk
from app.db.session import get_db
from app.schemas import KnowledgeCreate, KnowledgeImportOut, KnowledgeOut, KnowledgeSearchRequest
from app.services.knowledge_import_service import KnowledgeImportService
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


@router.post("", response_model=KnowledgeOut)
def create_knowledge(
    payload: KnowledgeCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> KnowledgeChunk:
    return KnowledgeService().create_chunk(db, payload)


@router.get("", response_model=list[KnowledgeOut])
def list_knowledge(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[KnowledgeChunk]:
    query = db.query(KnowledgeChunk)
    if project_id:
        query = query.filter(KnowledgeChunk.project_id == project_id)
    return query.order_by(KnowledgeChunk.id.desc()).all()


@router.post("/search", response_model=list[KnowledgeOut])
def search_knowledge(
    payload: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[KnowledgeChunk]:
    query_text = payload.query.strip()
    if not query_text:
        return []
    keyword = f"%{query_text}%"
    return (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.project_id == payload.project_id)
        .filter((KnowledgeChunk.title.ilike(keyword)) | (KnowledgeChunk.content.ilike(keyword)))
        .order_by(KnowledgeChunk.id.desc())
        .limit(payload.limit)
        .all()
    )


@router.post("/import", response_model=KnowledgeImportOut)
async def import_knowledge(
    project_id: int = Form(...),
    source_type: str = Form("requirement"),
    status: str = Form("active"),
    skill_name: str | None = Form(None),
    quality_score: int = Form(3),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> KnowledgeImportOut:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="单个文件不能超过 2MB")

    try:
        imported, skipped = KnowledgeImportService().import_file(
            db=db,
            project_id=project_id,
            filename=file.filename or "upload.txt",
            content=content,
            default_source_type=source_type,
            default_status=status,
            default_skill_name=skill_name,
            default_quality_score=quality_score,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return KnowledgeImportOut(imported=len(imported), skipped=skipped, items=imported)
