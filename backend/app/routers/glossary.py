from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.deps import require_role
from backend.app.db.session import get_connection

router = APIRouter(prefix="/glossary", tags=["glossary"])


@router.get("")
def list_glossary(
    status: str = "pending",
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("supervisor", "admin")),
):
    rows = conn.execute(
        text("SELECT id, language, term, maps_to_json, status FROM glossary_terms WHERE status = :status"),
        {"status": status},
    ).mappings().fetchall()
    return [dict(r) for r in rows]
