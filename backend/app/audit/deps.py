import functools
import inspect
from collections.abc import Callable
from typing import Any

from fastapi import Request

from backend.app.audit.chain import write_audit_entry


def audit(
    action: str,
    resource_type: str | None = None,
    case_id_from: str | None = None,
) -> Callable:
    """
    Decorator / helper for auditing endpoint operations.
    Extracts user, case_id, purpose, and IP from request and dependencies.
    Logs success on normal return.
    """
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                res = await func(*args, **kwargs)
                _record_from_call(action, resource_type, case_id_from, res, kwargs)
                return res
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                res = func(*args, **kwargs)
                _record_from_call(action, resource_type, case_id_from, res, kwargs)
                return res
            return sync_wrapper
    return decorator


def _record_from_call(
    action: str,
    resource_type: str | None,
    case_id_from: str | None,
    response: Any,
    kwargs: dict[str, Any],
) -> None:
    # 1. Extract request if present
    request: Request | None = kwargs.get("request")
    if request is None:
        for v in kwargs.values():
            if isinstance(v, Request):
                request = v
                break

    # 2. Extract user
    user: dict[str, Any] | None = kwargs.get("current_user")
    if user is None and "case_access_info" in kwargs and isinstance(kwargs["case_access_info"], dict):
        user = kwargs["case_access_info"].get("user")
    if user is None and request and hasattr(request.state, "user"):
        user = getattr(request.state, "user", None)

    user_id = user.get("id") if user else None
    username = user.get("username") if user else None
    role = user.get("role") if user else None

    # 3. Extract case_id and purpose
    case_id: str | None = None
    if case_id_from and case_id_from in kwargs:
        case_id = str(kwargs[case_id_from])
    elif "case_id" in kwargs:
        case_id = str(kwargs["case_id"])
    elif "case_access_info" in kwargs and isinstance(kwargs["case_access_info"], dict):
        case_dict = kwargs["case_access_info"].get("case", {})
        case_id = case_dict.get("id")

    purpose: str | None = kwargs.get("purpose")
    if purpose is None and "case_access_info" in kwargs and isinstance(kwargs["case_access_info"], dict):
        purpose = kwargs["case_access_info"].get("purpose")
    if purpose is None and request:
        purpose = request.headers.get("x-access-purpose")

    ip: str | None = None
    user_agent: str | None = None
    if request:
        ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    # 4. Extract resource_id
    resource_id: str | None = None
    if isinstance(response, dict) and "id" in response:
        resource_id = str(response["id"])
    elif case_id:
        resource_id = case_id
    elif "user_id" in kwargs:
        resource_id = str(kwargs["user_id"])
    elif "id" in kwargs:
        resource_id = str(kwargs["id"])

    # 5. Status code (default 200 or 201 for creates)
    status_code = 201 if action.endswith(".create") else 200

    details: dict[str, Any] = {}
    if isinstance(response, dict):
        # Do not include sensitive tokens or passwords in details
        filtered_details = {k: v for k, v in response.items() if k not in ("access_token", "password", "password_hash")}
        details.update(filtered_details)

    write_audit_entry(
        action=action,
        user_id=user_id,
        username=username,
        role=role,
        resource_type=resource_type,
        resource_id=resource_id,
        case_id=case_id,
        purpose=purpose,
        ip=ip,
        user_agent=user_agent,
        status_code=status_code,
        details=details,
    )
