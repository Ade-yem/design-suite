"""
storage/file_backends/local.py
===============================
Local filesystem file storage backend.

Used in development. Saves uploaded files under ``settings.UPLOAD_DIR``
with a millisecond timestamp prefix to prevent name collisions.

This is a direct extraction of the original ``FileHandler`` class, now
implementing the ``FileStorageBackend`` interface so it can be swapped
for the Cloudinary backend in production.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from config import settings, ACCEPTED_EXTENSIONS
from middleware.error_handler import StructuralError
from storage.file_backends.base import FileStorageBackend

# Project identifiers and stored filenames must be simple, separator-free tokens.
# This blocks path-traversal (``..``, ``/``, ``\``, null bytes) before any path
# is constructed from caller-supplied input.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_segment(segment: str, kind: str) -> str:
    """
    Reject a path segment that could escape the storage root.

    Parameters
    ----------
    segment : str
        Caller-supplied project id or filename.
    kind : str
        Human-readable label for error details ("project_id" / "filename").

    Returns
    -------
    str
        The validated segment.

    Raises
    ------
    StructuralError
        ``INVALID_PATH`` — segment is empty, "."/"..", or contains separators.
    """
    if not segment or segment in (".", "..") or not _SAFE_SEGMENT.match(segment):
        raise StructuralError(
            "INVALID_PATH",
            details={"message": f"Invalid {kind}.", "received": segment},
            status_code=400,
        )
    return segment


class LocalFileBackend(FileStorageBackend):
    """
    Saves uploaded DXF/PDF files to the local filesystem.

    Files are stored under:
        ``{UPLOAD_DIR}/{project_id}/{timestamp}_{original_filename}``

    Attributes
    ----------
    base_dir : Path
        Root directory for all project uploads (from ``settings.UPLOAD_DIR``).
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or settings.UPLOAD_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        """Return (and create) the per-project upload subdirectory."""
        _validate_segment(project_id, "project_id")
        d = self.base_dir / project_id
        # Defence in depth: ensure the resolved path stays under the storage root.
        if not d.resolve().is_relative_to(self.base_dir.resolve()):
            raise StructuralError(
                "INVALID_PATH",
                details={"message": "Resolved path escapes the storage root."},
                status_code=400,
            )
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save(self, project_id: str, file: UploadFile) -> str:
        """
        Save the upload to disk and return the absolute path as a string.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        file : UploadFile
            FastAPI upload file (DXF or PDF).

        Returns
        -------
        str
            Absolute path of the saved file.

        Raises
        ------
        StructuralError
            ``UNSUPPORTED_FILE`` — unsupported extension.
            ``FILE_TOO_LARGE``  — file exceeds ``settings.max_upload_bytes``.
        """
        original_name = file.filename or "upload"
        suffix = Path(original_name).suffix.lower()
        if suffix not in ACCEPTED_EXTENSIONS:
            raise StructuralError(
                "UNSUPPORTED_FILE",
                details={"received": suffix, "accepted": list(ACCEPTED_EXTENSIONS)},
                status_code=400,
            )

        # Check magic bytes for content validation (H6)
        header = await file.read(1024)
        await file.seek(0)

        is_valid = False
        if suffix == ".pdf":
            is_valid = header.startswith(b"%PDF")
        elif suffix == ".dxf":
            stripped = header.strip()
            is_valid = (
                header.startswith(b"AutoCAD Binary DXF") or
                stripped.startswith(b"0") or
                stripped.startswith(b"999") or
                b"SECTION" in stripped[:100]
            )

        if not is_valid:
            raise StructuralError(
                "UNSUPPORTED_FILE",
                details={"message": "File content does not match its extension type."},
                status_code=400,
            )

        timestamp = int(time.time() * 1000)
        safe_name = f"{timestamp}_{Path(original_name).name}"
        dest = self._project_dir(project_id) / safe_name

        total_bytes = 0
        chunk_size = 1024 * 1024  # 1 MB
        with dest.open("wb") as f:
            while chunk := await file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    dest.unlink(missing_ok=True)
                    raise StructuralError("FILE_TOO_LARGE", status_code=413)
                f.write(chunk)

        return str(dest)

    async def get_url(self, project_id: str, filename: str) -> Optional[str]:
        """
        Resolve a file by name within the project directory.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        filename : str
            Basename of the stored file.

        Returns
        -------
        str | None
            Absolute path string, or None if not found.
        """
        _validate_segment(filename, "filename")
        candidate = self._project_dir(project_id) / filename
        return str(candidate) if candidate.exists() else None

    def list_files(self, project_id: str) -> list[str]:
        """
        List all filenames in a project's upload directory.

        Parameters
        ----------
        project_id : str
            Owning project identifier.

        Returns
        -------
        list[str]
            Sorted list of file basenames.
        """
        _validate_segment(project_id, "project_id")
        d = self.base_dir / project_id
        if not d.exists():
            return []
        return sorted(f.name for f in d.iterdir() if f.is_file())

    def delete_project(self, project_id: str) -> None:
        """
        Remove the entire project upload directory and all its files.

        Parameters
        ----------
        project_id : str
            Owning project whose files should be purged.
        """
        _validate_segment(project_id, "project_id")
        d = self.base_dir / project_id
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
