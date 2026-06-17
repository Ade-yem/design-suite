"""
Rate-limiting wiring test.

The shared limiter is disabled under APP_ENV=test so the rest of the suite is
not throttled.  Here we build a tiny app with the same limiter, enable it, and
confirm the 429 path works end-to-end (decorator + middleware + handler).
"""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from middleware.rate_limit import limiter


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.post("/thing")
    @limiter.limit("2/minute")
    async def thing(request: Request):  # noqa: ANN001
        return {"ok": True}

    return app


def test_returns_429_after_limit_exceeded():
    was_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        client = TestClient(_build_app())
        assert client.post("/thing").status_code == 200
        assert client.post("/thing").status_code == 200
        # Third call within the window is throttled.
        assert client.post("/thing").status_code == 429
    finally:
        limiter.reset()
        limiter.enabled = was_enabled


def test_disabled_limiter_never_throttles():
    was_enabled = limiter.enabled
    limiter.enabled = False
    limiter.reset()
    try:
        client = TestClient(_build_app())
        for _ in range(5):
            assert client.post("/thing").status_code == 200
    finally:
        limiter.reset()
        limiter.enabled = was_enabled
