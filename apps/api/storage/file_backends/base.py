"""
storage/file_backends/base.py
==============================
Abstract base class for file storage backends.

All file storage implementations (local filesystem, Cloudinary, S3, etc.)
must subclass ``FileStorageBackend`` and implement all abstract methods.
This ensures routers and tests can depend on the interface without knowing
the concrete implementation.

Switch backends by setting ``FILE_STORAGE_BACKEND`` in ``.env``:
  - ``local``      → LocalFileBackend  (development)
  - ``cloudinary`` → CloudinaryFileBackend  (production)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import UploadFile


class FileStorageBackend(ABC):
    """
    Abstract interface for project file storage.

    All methods are async to support both local I/O and remote HTTP uploads
    without changing call sites.

    Methods
    -------
    save(project_id, file) → str
        Persist the uploaded file and return a URL or local path.
    get_url(project_id, filename) → str | None
        Resolve a stored file URL/path by filename.
    list_files(project_id) → list[str]
        List all file names uploaded to a project.
    delete_project(project_id) → None
        Remove all files associated with a project.
    """

    @abstractmethod
    async def save(self, project_id: str, file: UploadFile) -> str:
        """
        Persist an uploaded file for a project.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        file : UploadFile
            FastAPI upload file object (DXF or PDF).

        Returns
        -------
        str
            A URL (Cloudinary) or absolute path (local) identifying the saved file.

        Raises
        ------
        StructuralError
            ``UNSUPPORTED_FILE`` if the extension is not ``.dxf`` or ``.pdf``.
            ``FILE_TOO_LARGE`` if the upload exceeds the configured limit.
        """

    @abstractmethod
    async def get_url(self, project_id: str, filename: str) -> Optional[str]:
        """
        Resolve a stored file reference by filename.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        filename : str
            Basename of the file (as returned by ``list_files``).

        Returns
        -------
        str | None
            URL or path, or None if the file does not exist.
        """

    @abstractmethod
    def list_files(self, project_id: str) -> list[str]:
        """
        List all filenames uploaded to a project.

        Parameters
        ----------
        project_id : str
            Owning project identifier.

        Returns
        -------
        list[str]
            Sorted list of file basenames.
        """

    @abstractmethod
    def delete_project(self, project_id: str) -> None:
        """
        Remove all files associated with a project.

        Parameters
        ----------
        project_id : str
            Owning project whose files should be purged.
        """
