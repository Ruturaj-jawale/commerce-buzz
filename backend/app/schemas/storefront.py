"""Storefront API schemas."""

from pydantic import BaseModel, Field


class StorefrontRead(BaseModel):
    id: int
    name: str
    source: str = Field(validation_alias="provider")
    store_url: str
    status: str

    model_config = {"from_attributes": True}


class StorefrontCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")
    store_url: str = Field(min_length=1, max_length=255)
    webhook_secret: str | None = Field(default=None, min_length=16, max_length=128)
