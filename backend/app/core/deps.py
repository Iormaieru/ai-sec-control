import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.audit.context import current_actor_id
from app.auth.models import User, UserRole
from app.core.security import decode_access_token
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No se pudo validar la credencial",
    headers={"WWW-Authenticate": "Bearer"},
)


def _load_active_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Valida el JWT y trae al usuario. Es sync (consulta la base) y por lo
    tanto corre en un threadpool: cualquier ContextVar que se asigne acá se
    pierde (el threadpool trabaja sobre una copia del contexto). Por eso el
    actor se asigna en get_current_user, que es async."""
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise _CREDENTIALS_EXCEPTION
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user


async def get_current_user(user: User = Depends(_load_active_user)) -> User:
    # async a propósito: corre en el contexto del request, así que el actor
    # queda visible para el endpoint (que corre en un threadpool con una
    # copia de este contexto) y para los hooks de auditoría de app/audit.
    # Toda mutación del resto del request queda atribuida a este usuario.
    current_actor_id.set(user.id)
    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No tenés permisos para esta acción"
            )
        return user

    return dependency


require_admin = require_role(UserRole.ADMIN)
