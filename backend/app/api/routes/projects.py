from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Project
from app.db.session import get_db
from app.schemas import ProjectCreate, ProjectOut

router = APIRouter()


@router.post("", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _user=Depends(get_current_user)) -> list[Project]:
    return db.query(Project).order_by(Project.id.desc()).all()
