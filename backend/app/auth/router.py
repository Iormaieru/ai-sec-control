import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import User
from app.auth.schemas import TokenResponse, UserCreate, UserOut
from app.core.deps import get_current_user, require_admin
from app.core.security import create_access_token
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    user = service.authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        # Nunca se loguea la contraseña. El usuario sí: permite alertar en
        # Dynatrace por intentos fallidos repetidos (no hay límite de intentos).
        logger.warning("login_failed", extra={"username": form_data.username})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("login_ok", extra={"username": user.username, "role": user.role.value})
    token = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> User:
    try:
        return service.create_user(
            db,
            username=payload.username,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El nombre de usuario ya existe"
        ) from exc


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
