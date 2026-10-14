"""Environment-based application settings."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="saas-mcp", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    database_url: str = Field(default="sqlite:///./saas_mcp.db", alias="DATABASE_URL")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    mcp_server_name: str = Field(default="saas-mcp", alias="MCP_SERVER_NAME")
    mcp_server_version: str = Field(default="0.1.0", alias="MCP_SERVER_VERSION")
    cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="CORS_ORIGINS",
    )
    ingestion_worker_max_attempts: int = Field(default=3, alias="INGESTION_WORKER_MAX_ATTEMPTS")
    ingestion_worker_lease_seconds: int = Field(default=300, alias="INGESTION_WORKER_LEASE_SECONDS")
    max_ingestion_payload_bytes: int = Field(default=262144, alias="MAX_INGESTION_PAYLOAD_BYTES")
    max_import_file_bytes: int = Field(default=5242880, alias="MAX_IMPORT_FILE_BYTES")
    max_import_rows: int = Field(default=10000, alias="MAX_IMPORT_ROWS")
    pdf_ocr_enabled: bool = Field(default=False, alias="PDF_OCR_ENABLED")
    pdf_ocr_language: str = Field(default="eng", alias="PDF_OCR_LANGUAGE")
    pdf_ocr_dpi: int = Field(default=200, alias="PDF_OCR_DPI", ge=72, le=300)
    pdf_ocr_max_pages: int = Field(default=20, alias="PDF_OCR_MAX_PAGES", ge=1, le=100)
    bootstrap_token: str = Field(default="", alias="BOOTSTRAP_TOKEN")
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")
    api_key_pepper: str = Field(default="", alias="API_KEY_PEPPER")
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    jwt_expire_minutes: int = Field(default=720, alias="JWT_EXPIRE_MINUTES")

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env == "production" and (self.debug or self.secret_key == "change-me" or not self.bootstrap_token or not self.api_key_pepper):
            raise ValueError("Production requires DEBUG=false, a non-default SECRET_KEY, BOOTSTRAP_TOKEN, and API_KEY_PEPPER")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
