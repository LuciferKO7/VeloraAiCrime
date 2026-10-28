from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.deps import require_role
from backend.app.db.session import get_connection

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("auditor", "admin")),
):
    rows = conn.execute(text("SELECT seq, ts, user_id, username, role, action, resource_type, resource_id, case_id, status_code FROM audit_log ORDER BY seq DESC LIMIT 50")).mappings().fetchall()
    return [dict(r) for r in rows]
