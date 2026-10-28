from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.audit.chain import write_audit_entry
from backend.app.auth.deps import get_current_user
from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.core.security import create_access_token, verify_password
from backend.app.db.session import get_connection

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserSummary(BaseModel):
    id: str
    username: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    body: LoginRequest,
    conn: Connection = Depends(get_connection),
):
    now = datetime.now(UTC)
    username = body.username.strip()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    row = conn.execute(
        text(
            """
            SELECT id, username, full_name, role, password_hash, is_active, failed_logins, locked_until
            FROM users
            WHERE username = :username
            """
        ),
        {"username": username},
    ).mappings().fetchone()

    if not row:
        write_audit_entry(
            conn,
            action="auth.login_failed",
            username=username,
            ip=client_ip,
            user_agent=user_agent,
            status_code=401,
            details={"username": username, "reason": "User not found"},
        )
        raise AppError("AUTH_INVALID", "Invalid username or password")

    if not row["is_active"]:
        write_audit_entry(
            conn,
            action="auth.login_failed",
            user_id=row["id"],
            username=username,
            role=row["role"],
            ip=client_ip,
            user_agent=user_agent,
            status_code=401,
            details={"username": username, "reason": "Account is disabled"},
        )
        raise AppError("AUTH_INVALID", "Account is disabled")

    # Check lock
    locked_until_str = row["locked_until"]
    if locked_until_str:
        try:
            locked_until = datetime.fromisoformat(locked_until_str)
            if locked_until > now:
                write_audit_entry(
                    conn,
                    action="auth.login_failed",
                    user_id=row["id"],
                    username=username,
                    role=row["role"],
                    ip=client_ip,
                    user_agent=user_agent,
                    status_code=423,
                    details={"username": username, "reason": "Account locked", "locked_until": locked_until_str},
                )
                raise AppError("ACCOUNT_LOCKED", f"Account is locked until {locked_until_str}")
            else:
                # Lock expired, reset
                conn.execute(
                    text("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = :id"),
                    {"id": row["id"]},
                )
                conn.commit()
        except ValueError:
            pass

    # Verify password
    if not verify_password(body.password, row["password_hash"]):
        new_failed = row["failed_logins"] + 1
        lock_time = None
        if new_failed >= 5:
            lock_time = (now + timedelta(minutes=15)).isoformat()
            conn.execute(
                text("UPDATE users SET failed_logins = :failed, locked_until = :locked WHERE id = :id"),
                {"failed": new_failed, "locked": lock_time, "id": row["id"]},
            )
            conn.commit()
            write_audit_entry(
                conn,
                action="auth.login_failed",
                user_id=row["id"],
                username=username,
                role=row["role"],
                ip=client_ip,
                user_agent=user_agent,
                status_code=423,
                details={"username": username, "reason": "5 failed login attempts", "locked_until": lock_time},
            )
            raise AppError("ACCOUNT_LOCKED", "Account locked for 15 minutes due to 5 failed login attempts")

        conn.execute(
            text("UPDATE users SET failed_logins = :failed WHERE id = :id"),
            {"failed": new_failed, "id": row["id"]},
        )
        conn.commit()
        write_audit_entry(
            conn,
            action="auth.login_failed",
            user_id=row["id"],
            username=username,
            role=row["role"],
            ip=client_ip,
            user_agent=user_agent,
            status_code=401,
            details={"username": username, "reason": "Invalid password", "failed_count": new_failed},
        )
        raise AppError("AUTH_INVALID", "Invalid username or password")

    # Success: reset failed logins, update last login
    conn.execute(
        text("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = :now WHERE id = :id"),
        {"now": now.isoformat(), "id": row["id"]},
    )
    conn.commit()

    token = create_access_token(sub=row["id"], role=row["role"])
    expires_in = settings.JWT_EXPIRE_MINUTES * 60

    write_audit_entry(
        conn,
        action="auth.login",
        user_id=row["id"],
        username=row["username"],
        role=row["role"],
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={"username": row["username"]},
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserSummary(
            id=row["id"],
            username=row["username"],
            full_name=row["full_name"],
            role=row["role"],
        ),
    )


@router.post("/logout")
def logout(
    request: Request,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    write_audit_entry(
        conn,
        action="auth.logout",
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        ip=client_ip,
        user_agent=user_agent,
        status_code=200,
        details={},
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserSummary)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserSummary(
        id=current_user["id"],
        username=current_user["username"],
        full_name=current_user["full_name"],
        role=current_user["role"],
    )
