"""
storage/file_handler.py
=======================
File storage factory — returns the correct backend based on ``settings.FILE_STORAGE_BACKEND``.

Public interface
----------------
``file_handler``  : FileStorageBackend singleton

    Use ``file_handler`` across all routers instead of instantiating a backend directly.

Backend selection (set in .env)
--------------------------------
    FILE_STORAGE_BACKEND=local        → LocalFileBackend  (default, development)
    FILE_STORAGE_BACKEND=cloudinary   → CloudinaryFileBackend  (production)

Adding a new backend
--------------------
1. Create ``storage/file_backends/my_backend.py`` implementing ``FileStorageBackend``.
2. Add a branch in ``_build_file_backend()`` below.
3. Set ``FILE_STORAGE_BACKEND=my_backend`` in ``.env``.
"""

from __future__ import annotations

from config import settings
from storage.file_backends.base import FileStorageBackend


def _build_file_backend() -> FileStorageBackend:
    """
    Instantiate and return the configured file storage backend.

    Backend is selected from ``settings.FILE_STORAGE_BACKEND``:

    - ``"local"``      → ``LocalFileBackend``      (writes to disk, no external deps)
    - ``"cloudinary"`` → ``CloudinaryFileBackend``  (streams to Cloudinary)

    Returns
    -------
    FileStorageBackend
        Concrete backend instance.

    Raises
    ------
    ValueError
        If ``FILE_STORAGE_BACKEND`` is set to an unknown value.
    """
    backend = settings.FILE_STORAGE_BACKEND.lower()

    if backend == "local":
        from storage.file_backends.local import LocalFileBackend
        return LocalFileBackend()

    if backend == "cloudinary":
        from storage.file_backends.cloudinary import CloudinaryFileBackend
        return CloudinaryFileBackend()

    raise ValueError(
        f"Unknown FILE_STORAGE_BACKEND: '{backend}'. "
        "Expected 'local' or 'cloudinary'."
    )


# ── Singleton ────────────────────────────────────────────────────────────────
file_handler: FileStorageBackend = _build_file_backend()
