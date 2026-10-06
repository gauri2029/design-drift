from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    # 8 is the floor, not the advice. The cap exists because argon2 hashes
    # whatever it's given and a megabyte-long password is a free way to burn
    # CPU on an unauthenticated endpoint.
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    created_at: datetime


class TokenResponse(BaseModel):
    """What both signup and login return: the token plus who it belongs to,
    so the frontend doesn't need a second round trip to render a name."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
