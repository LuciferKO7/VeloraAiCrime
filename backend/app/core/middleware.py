
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_JSON_SIZE = 2 * 1024 * 1024  # 2 MB limit for standard JSON payloads
MAX_UPLOAD_SIZE = 15 * 1024 * 1024  # 15 MB limit for file/image uploads


class RequestSizeLimitMiddleware:
    """
    Middleware that enforces request body size limits without buffering arbitrarily large
    payloads into memory (§12 Step B12).
    Rejects oversized requests with standard 413 REQUEST_TOO_LARGE structured response.
    """

    def __init__(self, app: ASGIApp, max_json_size: int = MAX_JSON_SIZE, max_upload_size: int = MAX_UPLOAD_SIZE):
        self.app = app
        self.max_json_size = max_json_size
        self.max_upload_size = max_upload_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").lower()
        path = scope.get("path", "")

        is_upload = "multipart/form-data" in content_type or "/faces" in path or "/transcribe" in path
        max_allowed = self.max_upload_size if is_upload else self.max_json_size

        content_length_str = headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > max_allowed:
                    response = JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": f"Request body exceeds maximum allowed size ({max_allowed} bytes)",
                                "details": {
                                    "max_bytes": max_allowed,
                                    "content_length": content_length,
                                },
                            }
                        },
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        # Also guard streaming / chunked uploads without Content-Length
        bytes_received = 0
        limit_exceeded = False

        async def custom_receive() -> Message:
            nonlocal bytes_received, limit_exceeded
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > max_allowed:
                    limit_exceeded = True
            return message

        try:
            await self.app(scope, custom_receive, send)
        except Exception:
            if limit_exceeded:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "REQUEST_TOO_LARGE",
                            "message": f"Request body exceeds maximum allowed size ({max_allowed} bytes)",
                            "details": {
                                "max_bytes": max_allowed,
                                "bytes_received": bytes_received,
                            },
                        }
                    },
                )
                await response(scope, receive, send)
                return
            raise


class SecurityHeadersMiddleware:
    """
    Middleware that adds baseline security headers to all responses without breaking
    frontend assets, CORS preflight, or streaming endpoints (§12 Step B12).
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add headers if not already set
                existing_names = {k.decode("latin1").lower() for k, _ in headers}

                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none';",
                    ),
                ]

                for key, val in security_headers:
                    if key.decode("latin1") not in existing_names:
                        headers.append((key, val))

                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
