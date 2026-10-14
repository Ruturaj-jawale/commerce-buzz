"""Organization and API-key request/response schemas."""

from pydantic import BaseModel, Field


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class UserRead(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserRead
    organization: OrganizationRead


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=120)
    organization_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    email: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=72)


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=72)


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization: OrganizationRead
    email: str


class ApiKeyCreated(BaseModel):
    id: int
    name: str
    key: str
    prefix: str


class BootstrapResponse(BaseModel):
    organization: OrganizationRead
    api_key: ApiKeyCreated


class RegisterResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization: OrganizationRead
    email: str
    api_key: ApiKeyCreated


class ApiKeyRotateRequest(BaseModel):
    name: str = Field(default="Rotated API key", min_length=2, max_length=80)
