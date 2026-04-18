"""
middleware/request_logger.py
============================
ASGI middleware that logs every HTTP request with method, path, status code,
and wall-clock duration.

Log format (INFO level)::

    [POST] /api/v1/analysis/PRJ-047/run  →  202  (12ms)
    [GET]  /api/v1/analysis/PRJ-047/status/JOB-023  →  200  (3ms)

This feeds the developer view and is also used to identify slow computation
modules during pipeline debugging.

Usage
-----
    from middleware.request_logger import RequestLoggerMiddleware
    app.add_middleware(RequestLoggerMiddleware)
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api.request")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    Starlette base middleware that records request timing for every HTTP call.

    Each log entry includes:
    - HTTP method
    - Path (with query string omitted for brevity)
    - Response status code
    - Duration in milliseconds

    Parameters
    ----------
    app : ASGIApp
        The downstream ASGI application — passed automatically by ``add_middleware``.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request, record timing, and log the result.

        Parameters
        ----------
        request : Request
            Incoming Starlette request.
        call_next : Callable
            Next middleware or route handler in the chain.

        Returns
        -------
        Response
            Unmodified response from the downstream handler.
        """
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "[%s] %s  →  %d  (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        # Attach timing header for frontend debugging
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response
