import uuid

from pydantic import BaseModel, ConfigDict

from app.auth.models import UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: UserRole = UserRole.USER


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool
