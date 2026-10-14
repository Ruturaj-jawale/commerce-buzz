"""Security-sensitive audit events. Never store secrets."""

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Organization


class AuditService:
    def record(self, db: Session, action: str, resource: str, organization: Organization | None = None, actor: str = "system") -> None:
        db.add(
            AuditLog(
                organization_id=organization.id if organization else None,
                actor=actor[:120],
                action=action,
                resource=resource[:120],
            )
        )
        db.commit()
