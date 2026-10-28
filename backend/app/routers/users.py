import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import require_role
from backend.app.core.errors import AppError
from backend.app.core.security import hash_password
from backend.app.db.session import atomic_mutation, get_connection

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    full_name: str
    role: str
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: int | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    is_active: int
    created_at: str
    last_login_at: str | None = None


@router.get("", response_model=list[UserResponse])
def list_users(
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    rows = conn.execute(
        text("SELECT id, username, full_name, role, is_active, created_at, last_login_at FROM users ORDER BY created_at")
    ).mappings().fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    request: Request,
    body: UserCreate,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    allowed_roles = ("investigator", "artist", "supervisor", "auditor", "admin")
    if body.role not in allowed_roles:
        raise AppError("VALIDATION_ERROR", f"Invalid role '{body.role}'. Must be one of {allowed_roles}")

    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :username"),
        {"username": body.username.strip()},
    ).fetchone()
    if existing:
        raise AppError("VALIDATION_ERROR", f"Username '{body.username}' is already taken")

    user_id = str(uuid.uuid4())
    pwd_hash = hash_password(body.password)
    now_iso = datetime.now(UTC).isoformat()

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        conn.execute(
            text(
                """
                INSERT INTO users (id, username, full_name, role, password_hash, is_active, failed_logins, created_at)
                VALUES (:id, :username, :full_name, :role, :pwd_hash, 1, 0, :created_at)
                """
            ),
            {
                "id": user_id,
                "username": body.username.strip(),
                "full_name": body.full_name.strip(),
                "role": body.role,
                "pwd_hash": pwd_hash,
                "created_at": now_iso,
            },
        )
        write_audit_entry(
            conn,
            action="user.create",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="user",
            resource_id=user_id,
            ip=client_ip,
            user_agent=user_agent,
            status_code=201,
            details={"created_user_id": user_id, "username": body.username.strip(), "role": body.role},
        )

    return UserResponse(
        id=user_id,
        username=body.username.strip(),
        full_name=body.full_name.strip(),
        role=body.role,
        is_active=1,
        created_at=now_iso,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    body: UserUpdate,
    request: Request,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(require_role("admin")),
):
    row = conn.execute(
        text("SELECT id, username, full_name, role, is_active, created_at, last_login_at FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().fetchone()
    if not row:
        raise AppError("NOT_FOUND", "User not found")

    updates = []
    params = {"id": user_id}

    if body.full_name is not None:
        updates.append("full_name = :full_name")
        params["full_name"] = body.full_name.strip()
    if body.role is not None:
        allowed_roles = ("investigator", "artist", "supervisor", "auditor", "admin")
        if body.role not in allowed_roles:
            raise AppError("VALIDATION_ERROR", f"Invalid role '{body.role}'")
        updates.append("role = :role")
        params["role"] = body.role
    if body.password is not None:
        updates.append("password_hash = :pwd_hash")
        params["pwd_hash"] = hash_password(body.password)
    if body.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = body.is_active

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with atomic_mutation(conn):
        if updates:
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = :id"
            conn.execute(text(sql), params)

        write_audit_entry(
            conn,
            action="user.update",
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            resource_type="user",
            resource_id=user_id,
            ip=client_ip,
            user_agent=user_agent,
            status_code=200,
            details={"updated_user_id": user_id, "fields": [k for k, v in body.model_dump(exclude_unset=True).items() if k != "password"]},
        )

    updated = conn.execute(
        text("SELECT id, username, full_name, role, is_active, created_at, last_login_at FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().fetchone()

    return dict(updated)
