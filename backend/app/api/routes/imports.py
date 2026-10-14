"""CSV/Excel import HTTP routes."""

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization
from app.db.database import get_db
from app.db.models import Organization
from app.schemas.imports import ImportBatchRead, ImportCreated, ImportStatusRead, MappingSetRequest, ValidationReport
from app.services.import_service import ImportService

router = APIRouter(prefix="/api/imports", tags=["imports"])
_service = ImportService()


@router.post("/file", response_model=ImportCreated, status_code=201)
async def upload_file_without_source(
    file: UploadFile,
    source_name: str | None = Form(default=None, max_length=120),
    source_label: str | None = Form(default=None, max_length=80),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ImportCreated:
    """Upload a file without selecting an existing commerce source.

    The service creates an organization-scoped generic file-import source so
    every import still lands in the same universal ingestion pipeline.
    """
    content = await file.read()
    return _service.create_upload_without_source(db, organization, file.filename or "upload", content, source_name, source_label)


@router.post("/sources/{storefront_id}", response_model=ImportCreated, status_code=201)
async def upload_import_file(
    storefront_id: int,
    file: UploadFile,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ImportCreated:
    content = await file.read()
    return _service.create_upload(db, organization, storefront_id, file.filename or "upload", content)


@router.get("", response_model=list[ImportBatchRead])
def list_imports(organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> list[ImportBatchRead]:
    return _service.list_batches(db, organization)


@router.get("/{batch_id}", response_model=ImportStatusRead)
def get_import(batch_id: int, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> ImportStatusRead:
    return _service.get_status(db, organization, batch_id)


@router.put("/{batch_id}/mapping", response_model=ValidationReport)
def set_import_mapping(
    batch_id: int,
    body: MappingSetRequest,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ValidationReport:
    return _service.set_mapping(db, organization, batch_id, body.mapping)


@router.post("/{batch_id}/import", response_model=ImportBatchRead)
def start_import(batch_id: int, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> ImportBatchRead:
    return _service.start_import(db, organization, batch_id)
