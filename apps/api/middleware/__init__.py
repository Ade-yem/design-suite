"""
middleware/__init__.py
======================
Middleware package for the Structural Design Copilot API.

Exports
-------
RequestLoggerMiddleware : ASGI request timing and logging middleware.
register_error_handlers : Function to attach global exception handlers.
StructuralError         : Domain-specific exception for the service layer.
"""

from .request_logger import RequestLoggerMiddleware
from .error_handler import register_error_handlers, StructuralError

__all__ = ["RequestLoggerMiddleware", "register_error_handlers", "StructuralError"]
