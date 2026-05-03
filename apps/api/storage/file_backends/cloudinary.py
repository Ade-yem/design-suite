"""
storage/file_backends/cloudinary.py
=====================================
Cloudinary file storage backend for production.

Streams DXF and PDF uploads directly to Cloudinary using ``resource_type="raw"``
(required for non-image binary files). Returns the secure HTTPS URL.

Configuration (.env)
--------------------
    FILE_STORAGE_BACKEND=cloudinary
    CLOUDINARY_CLOUD_NAME=your-cloud-name
    CLOUDINARY_API_KEY=your-api-key
    CLOUDINARY_API_SECRET=your-api-secret
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from fastapi import UploadFile

from config import settings, ACCEPTED_EXTENSIONS
from middleware.error_handler import StructuralError
from storage.file_backends.base import FileStorageBackend


class CloudinaryFileBackend(FileStorageBackend):
    """
    Stores uploaded DXF/PDF files in Cloudinary.

    Files are stored under the folder:
        ``design-suite/{project_id}/{timestamp}_{filename}``

    Cloudinary returns a secure HTTPS URL for each upload.

    Attributes
    ----------
    folder_prefix : str
        Top-level Cloudinary folder for all project uploads.
    """

    folder_prefix: str = "design-suite"

    def __init__(self) -> None:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )

    def _public_id(self, project_id: str, filename: str) -> str:
        """Build the Cloudinary public_id for a file."""
        return f"{self.folder_prefix}/{project_id}/{filename}"

    async def save(self, project_id: str, file: UploadFile) -> str:
        """
        Upload the file to Cloudinary and return the secure URL.

        Reads the entire file into memory before uploading (Cloudinary SDK
        requirement). Files larger than ``settings.max_upload_bytes`` are
        rejected before the upload is attempted.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        file : UploadFile
            FastAPI upload file (DXF or PDF).

        Returns
        -------
        str
            Cloudinary secure HTTPS URL.

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

        contents = await file.read()
        if len(contents) > settings.max_upload_bytes:
            raise StructuralError("FILE_TOO_LARGE", status_code=413)

        timestamp = int(time.time() * 1000)
        safe_name = f"{timestamp}_{Path(original_name).stem}"
        public_id = self._public_id(project_id, safe_name)

        result = cloudinary.uploader.upload(
            contents,
            public_id=public_id,
            resource_type="raw",    # required for non-image binary files (DXF, PDF)
            overwrite=False,
        )
        return result["secure_url"]

    async def get_url(self, project_id: str, filename: str) -> Optional[str]:
        """
        Build the Cloudinary URL for a stored file by name.

        Parameters
        ----------
        project_id : str
            Owning project identifier.
        filename : str
            Basename stored in the project's Cloudinary folder.

        Returns
        -------
        str | None
            Cloudinary HTTPS URL, or None if the resource does not exist.
        """
        public_id = self._public_id(project_id, filename)
        url, _ = cloudinary.utils.cloudinary_url(public_id, resource_type="raw")
        # Verify existence by attempting to fetch metadata (light API call)
        try:
            cloudinary.uploader.explicit(public_id, type="upload", resource_type="raw")
            return url
        except Exception:
            return None

    def list_files(self, project_id: str) -> list[str]:
        """
        List all files stored in a project's Cloudinary folder.

        Parameters
        ----------
        project_id : str
            Owning project identifier.

        Returns
        -------
        list[str]
            List of public_ids (filenames) sorted alphabetically.
        """
        folder = f"{self.folder_prefix}/{project_id}"
        try:
            result = cloudinary.api.resources(
                type="upload",
                resource_type="raw",
                prefix=folder,
                max_results=100,
            )
            return sorted(r["public_id"].split("/")[-1] for r in result.get("resources", []))
        except Exception:
            return []

    def delete_project(self, project_id: str) -> None:
        """
        Delete all Cloudinary resources for a project folder.

        Parameters
        ----------
        project_id : str
            Owning project whose files should be purged.
        """
        folder = f"{self.folder_prefix}/{project_id}"
        try:
            cloudinary.api.delete_resources_by_prefix(folder, resource_type="raw")
            cloudinary.api.delete_folder(folder)
        except Exception:
            pass   # Folder may not exist — non-fatal
