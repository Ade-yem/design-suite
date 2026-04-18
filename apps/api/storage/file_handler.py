"""
storage/file_handler.py
=======================
Filesystem persistence for uploaded DXF / PDF files.

Each project gets its own sub-directory under ``settings.UPLOAD_DIR``.
Files are saved with a timestamp prefix to avoid name collisions on re-upload.

Public interface
----------------
FileHandler.save(project_id, file)           → Path
FileHandler.get_path(project_id, filename)   → Path | None
FileHandler.list_files(project_id)           → list[str]
FileHandler.delete(project_id)               → None
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from config import settings, ACCEPTED_EXTENSIONS
from middleware.error_handler import StructuralError


class FileHandler:
    """
    Handles upload directory management and file persistence.

    Attributes
    ----------
    base_dir : Path
        Root upload directory (from ``settings.UPLOAD_DIR``).
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or settings.UPLOAD_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        """Return (and create) the project-specific upload directory."""
        d = self.base_dir / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save(self, project_id: str, file: UploadFile) -> Path:
        """
        Persist an uploaded file to the project directory.

        The file is read in 1 MB chunks to avoid exhausting memory on large uploads.
        A millisecond timestamp is prepended to the filename to prevent collisions.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        file : UploadFile
            FastAPI upload file object.

        Returns
        -------
        Path
            Absolute path to the saved file.

        Raises
        ------
        StructuralError
            ``UNSUPPORTED_FILE`` — if the file extension is not .dxf or .pdf.
            ``FILE_TOO_LARGE``  — if the content exceeds ``settings.max_upload_bytes``.
        """
        original_name = file.filename or "upload"
        suffix = Path(original_name).suffix.lower()
        if suffix not in ACCEPTED_EXTENSIONS:
            raise StructuralError(
                "UNSUPPORTED_FILE",
                details={"received": suffix, "accepted": list(ACCEPTED_EXTENSIONS)},
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

        return dest

    def get_path(self, project_id: str, filename: str) -> Optional[Path]:
        """
        Retrieve the absolute path for a named file within a project's upload directory.

        Parameters
        ----------
        project_id : str
            Project identifier.
        filename : str
            File name (basename only).

        Returns
        -------
        Path | None
            Resolved path, or None if the file does not exist.
        """
        candidate = self._project_dir(project_id) / filename
        return candidate if candidate.exists() else None

    def list_files(self, project_id: str) -> list[str]:
        """
        List all file names uploaded to a project.

        Parameters
        ----------
        project_id : str
            Project identifier.

        Returns
        -------
        list[str]
            File basenames sorted alphabetically.
        """
        d = self.base_dir / project_id
        if not d.exists():
            return []
        return sorted(f.name for f in d.iterdir() if f.is_file())

    def delete(self, project_id: str) -> None:
        """
        Delete the entire upload directory for a project.

        Parameters
        ----------
        project_id : str
            Project identifier whose files should be purged.
        """
        import shutil
        d = self.base_dir / project_id
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


# ── Singleton ────────────────────────────────────────────────────────────────
file_handler = FileHandler()
