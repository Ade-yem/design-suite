"""
storage/__init__.py
===================
Storage layer package for the Structural Design Copilot API.

Exports
-------
project_store : ProjectStore singleton — project CRUD and pipeline state machine.
job_store     : JobStore singleton  — async job lifecycle management.
file_handler  : FileHandler singleton — DXF/PDF file persistence.
"""

from .project_store import project_store, ProjectStore
from .job_store import job_store, JobStore
from .file_handler import file_handler, FileHandler

__all__ = [
    "project_store", "ProjectStore",
    "job_store", "JobStore",
    "file_handler", "FileHandler",
]
