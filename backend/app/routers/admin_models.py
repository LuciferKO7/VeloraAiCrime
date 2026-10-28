from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.deps import require_role
from backend.app.db.session import get_connection

router = APIRouter(prefix="/admin/models", tags=["admin-models"])


@router.get("")
def list_models(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    rows = conn.execute(text("SELECT id, name, role, version, is_active FROM model_registry")).mappings().fetchall()
    return [dict(r) for r in rows]
