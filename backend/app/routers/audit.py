import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import verify_audit_chain, write_audit_entry
from backend.app.auth.deps import require_role
from backend.app.core.errors import AppError
from backend.app.db.session import get_connection

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_COLUMNS = [
    "seq",
    "ts",
    "user_id",
    "username",
    "role",
    "action",
    "resource_type",
    "resource_id",
    "case_id",
    "purpose",
    "ip",
    "user_agent",
    "status_code",
    "details_json",
    "prev_hash",
    "entry_hash",
]

FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_csv_cell(value: Any) -> Any:
    """
    Sanitizes untrusted textual fields against CSV / spreadsheet formula injection (OWASP).
    If a string cell starts with formula markers (=, +, -, @), it is prefixed with a single quote (')
    in the exported CSV representation so spreadsheet engines treat it as plain text.
    The underlying audit database values remain untouched.
    """
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _build_audit_query(
    from_ts: str | None = None,
    to_ts: str | None = None,
    user_id: str | None = None,
    case_id: str | None = None,
    action: str | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> tuple[str, dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": limit}

    if from_ts:
        clauses.append("ts >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts:
        clauses.append("ts <= :to_ts")
        params["to_ts"] = to_ts
    if user_id:
        clauses.append("user_id = :user_id")
        params["user_id"] = user_id
    if case_id:
        clauses.append("case_id = :case_id")
        params["case_id"] = case_id
    if action:
        clauses.append("action = :action")
        params["action"] = action
    if cursor is not None:
        clauses.append("seq < :cursor")
        params["cursor"] = cursor

    col_list = ", ".join(AUDIT_COLUMNS)
    sql = f"SELECT {col_list} FROM audit_log WHERE {' AND '.join(clauses)} ORDER BY seq DESC LIMIT :limit"
    return sql, params


@router.get("")
def list_audit_logs(
    request: Request,
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    user_id: str | None = Query(None),
    case_id: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    cursor: int | None = Query(None),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("auditor", "admin")),
):
    sql, params = _build_audit_query(
        from_ts=from_ts,
        to_ts=to_ts,
        user_id=user_id,
        case_id=case_id,
        action=action,
        cursor=cursor,
        limit=limit,
    )
    rows = conn.execute(text(sql), params).mappings().fetchall()
    result = [dict(r) for r in rows]

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    write_audit_entry(
        conn,
        action="audit.view",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        resource_type="audit_log",
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={
            "from": from_ts,
            "to": to_ts,
            "user_id": user_id,
            "case_id": case_id,
            "action": action,
            "limit": limit,
            "cursor": cursor,
            "returned_count": len(result),
        },
    )

    return result


@router.get("/verify")
def verify_audit(
    request: Request,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("auditor", "admin")),
):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Record verification request without breaking chain validity
    write_audit_entry(
        conn,
        action="audit.verify",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        resource_type="audit_log",
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={},
    )

    result = verify_audit_chain(conn)
    return result


@router.get("/export")
def export_audit(
    request: Request,
    format: str = Query("json"),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    user_id: str | None = Query(None),
    case_id: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    cursor: int | None = Query(None),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("auditor", "admin")),
):
    fmt = format.lower().strip()
    if fmt not in ("csv", "json"):
        raise AppError("VALIDATION_ERROR", f"Invalid export format '{format}'. Supported formats: csv, json")

    sql, params = _build_audit_query(
        from_ts=from_ts,
        to_ts=to_ts,
        user_id=user_id,
        case_id=case_id,
        action=action,
        cursor=cursor,
        limit=limit,
    )
    rows = conn.execute(text(sql), params).mappings().fetchall()
    result = [dict(r) for r in rows]

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    write_audit_entry(
        conn,
        action="audit.export",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        resource_type="audit_log",
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={
            "format": fmt,
            "from": from_ts,
            "to": to_ts,
            "user_id": user_id,
            "case_id": case_id,
            "action": action,
            "limit": limit,
            "cursor": cursor,
            "exported_count": len(result),
        },
    )

    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(AUDIT_COLUMNS)
        for r in result:
            writer.writerow([sanitize_csv_cell(r.get(c)) for c in AUDIT_COLUMNS])
        csv_bytes = out.getvalue().encode("utf-8")
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )
    else:
        json_str = json.dumps(result, indent=2, ensure_ascii=False)
        return Response(
            content=json_str.encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit_export.json"},
        )
