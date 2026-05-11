from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ProjectEnvironment
from app.db.session import get_db
from app.schemas import ProjectEnvironmentCreate, ProjectEnvironmentOut

router = APIRouter()


@router.post("", response_model=ProjectEnvironmentOut)
def create_environment(
    payload: ProjectEnvironmentCreate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> ProjectEnvironment:
    if payload.is_default:
        db.query(ProjectEnvironment).filter(ProjectEnvironment.project_id == payload.project_id).update({"is_default": False})

    environment = ProjectEnvironment(**payload.model_dump())
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment


@router.get("", response_model=list[ProjectEnvironmentOut])
def list_environments(
    project_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ProjectEnvironment]:
    return (
        db.query(ProjectEnvironment)
        .filter(ProjectEnvironment.project_id == project_id)
        .order_by(ProjectEnvironment.is_default.desc(), ProjectEnvironment.id.desc())
        .all()
    )


@router.delete("/{environment_id}")
def delete_environment(
    environment_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict[str, str]:
    environment = db.get(ProjectEnvironment, environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail="项目环境不存在")
    db.delete(environment)
    db.commit()
    return {"status": "deleted"}
