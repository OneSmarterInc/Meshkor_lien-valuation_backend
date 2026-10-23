"""Write one audit line. Never raises (an audit failure must not break the request)."""
import logging

log_ = logging.getLogger("meshkor.audit")


def actor_text(user) -> str:
    if user is None or not getattr(user, "is_authenticated", False):
        return "system"
    name = (user.get_full_name() or "").strip() or user.email or user.username
    p = getattr(user, "profile", None)
    if p and p.firm_id:
        return f"{name} ({p.firm.name})"
    return f"{name} (MeshKor)" if p else name


def log(user, action: str, detail: str = "", case=None) -> None:
    from .models import AuditEntry
    try:
        AuditEntry.objects.create(actor_user=user if getattr(user, "is_authenticated", False) else None,
                                  actor=actor_text(user), action=action, detail=detail or "", case=case)
    except Exception:  # noqa: BLE001
        log_.exception("audit write failed: %s %s", action, detail)
