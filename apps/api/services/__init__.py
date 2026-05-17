"""
services/
=========
Shared service layer — contains all business logic for the pipeline.

Both the FastAPI routers (HTTP interface) and LangGraph agent nodes import
from this package directly.  Neither layer performs calculations itself.

Modules
-------
files    : DXF/PDF parsing, geometry storage, scale management, Gate 1 verification.
loading  : Load definition storage, combination engine, validation.
analysis : Analysis engine orchestration, result storage.
design   : Design suite orchestration, override application, result storage.
"""
