from sqlalchemy.orm import Session

from .models import AuditLog


def write_audit(db: Session, user, action: str, entity: str, entity_id, before=None, after=None, reason=None):
    """Adds the row to the caller's session, so it commits or rolls back with the change (ADR-14).
    `user=None` means the system acted (worker, auto-approval)."""
    db.add(AuditLog(actor=getattr(user, "id", None), actor_email=getattr(user, "email", "system"),
                    action=action, entity=entity, entity_id=str(entity_id), before=before, after=after, reason=reason))
