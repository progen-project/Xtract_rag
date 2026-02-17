"""
HTTP Request/Response logging middleware for FastAPI.

Logs every request with:
- Method, path, size
- Response status, duration, size
- Unique request_id for correlation across all log lines
"""
import time
import uuid
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import request_id_var

logger = logging.getLogger("petrorag.middleware")


def _format_bytes(size: int) -> str:
    """Format byte count to human-readable string."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs every HTTP request and response.
    
    Assigns a unique request_id to each request and stores it
    in a contextvars.ContextVar so ALL downstream loggers
    automatically include it.
    """

    # Paths to skip logging (health checks, static files)
    SKIP_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/redoc", "/favicon.ico"})

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip noisy endpoints
        if request.url.path in self.SKIP_PATHS or request.url.path.startswith(("/extracted_images/", "/chat_images/")):
            return await call_next(request)

        # Generate and set request ID
        req_id = uuid.uuid4().hex[:12]
        token = request_id_var.set(req_id)

        method = request.method
        path = request.url.path
        query = str(request.url.query)
        full_path = f"{path}?{query}" if query else path
        client_ip = request.client.host if request.client else "unknown"

        # Request size
        content_length = request.headers.get("content-length", "0")
        try:
            req_size = int(content_length)
        except (ValueError, TypeError):
            req_size = 0

        logger.info(
            f"→ {method} {full_path} {_format_bytes(req_size)}",
            extra={"method": method, "path": path, "client_ip": client_ip, "request_size": req_size}
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000)
            logger.error(
                f"✗ {method} {full_path} {duration_ms}ms — {type(exc).__name__}: {exc}",
                extra={"method": method, "path": path, "duration_ms": duration_ms, "status_code": 500},
                exc_info=True,
            )
            request_id_var.reset(token)
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000)
        status = response.status_code

        # Response size
        resp_size = 0
        if hasattr(response, "headers"):
            try:
                resp_size = int(response.headers.get("content-length", "0"))
            except (ValueError, TypeError):
                resp_size = 0

        # Choose log level based on status code
        if status >= 500:
            log_fn = logger.error
        elif status >= 400:
            log_fn = logger.warning
        else:
            log_fn = logger.info

        # Format duration nicely
        if duration_ms >= 1000:
            dur_str = f"{duration_ms / 1000:.1f}s"
        else:
            dur_str = f"{duration_ms}ms"

        log_fn(
            f"← {status} {method} {full_path} {dur_str} {_format_bytes(resp_size)}",
            extra={
                "method": method, "path": path,
                "status_code": status, "duration_ms": duration_ms,
                "response_size": resp_size, "client_ip": client_ip,
            }
        )

        # Add request ID to response headers for client-side correlation
        response.headers["X-Request-ID"] = req_id

        request_id_var.reset(token)
        return response
