from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import TokenOut, UserLogin, UserOut, UserRegister
from app.services.auth_service import authenticate_user, create_access_token, hash_password

router = APIRouter()


@router.post("/register", response_model=TokenOut)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> TokenOut:
    user_count = db.query(User).count()
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role="admin" if user_count == 0 else "tester",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号已存在")
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user), user=user)


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenOut:
    user = authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return TokenOut(access_token=create_access_token(user), user=user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
