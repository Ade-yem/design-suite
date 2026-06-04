"""
schemas/artifact.py
===================
Domain schema for artifact snapshot records.

``ArtifactRecord`` is the backend-agnostic representation returned by both the
memory and postgres artifact stores — mirroring how ``project_store`` returns
``ProjectResponse`` regardless of the active backend. Routers map this record
onto the public ``ArtifactResponse`` envelope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ArtifactRecord(BaseModel):
    """
    Backend-agnostic artifact snapshot.

    Attributes
    ----------
    artifact_id : str
        Unique snapshot identifier (``ART-`` prefixed).
    project_id : str
        Owning project.
    stage : str
        Pipeline stage value (e.g. ``"verification"``).
    status : str
        Status badge (``signed_off`` | ``in_review`` | ``pending``).
    content : str | None
        Serialized snapshot payload (JSON string). Omitted from list responses.
    preview_url : str | None
        Optional URL to a rendered preview.
    created_at : datetime
        UTC creation timestamp.
    author_id : UUID | None
        FK → users.id of the engineer who approved the gate.
    author : str | None
        Denormalized author email for display.
    """

    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    project_id: str
    stage: str
    status: str
    content: Optional[str] = None
    preview_url: Optional[str] = None
    created_at: datetime
    author_id: Optional[UUID] = None
    author: Optional[str] = None
