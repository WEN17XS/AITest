from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import KnowledgeChunk
from app.db.session import get_db
from app.schemas import KnowledgeCreate, KnowledgeOut, KnowledgeSearchRequest
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
