"""
tests/unit/storage/test_artifact_store.py
=========================================
Unit tests for the in-memory artifact store (MemoryArtifactStore).

Covers snapshot creation (dict and string payloads), project-scoped listing
and ordering, single retrieval, and isolation between projects. These tests are
backend-agnostic in intent but exercise the memory backend, which is what runs
in development and the test suite.
"""

from __future__ import annotations

import json
import uuid

import pytest

from db.models.artifact import ArtifactStage
from storage.artifact_store import MemoryArtifactStore


@pytest.fixture
def store() -> MemoryArtifactStore:
    return MemoryArtifactStore()


GEOMETRY = {"members": [{"member_id": "B-01", "member_type": "beam"}], "scale": {"factor": 1.0}}


class TestCreateSnapshot:
    async def test_returns_record_with_expected_fields(self, store: MemoryArtifactStore) -> None:
        """A snapshot is created with a generated ID, signed_off status, and author."""
        author_id = uuid.uuid4()
        record = await store.create_snapshot(
            "PRJ-ABC",
            ArtifactStage.VERIFICATION,
            content=GEOMETRY,
            author_id=author_id,
            author_email="eng@example.com",
        )

        assert record.artifact_id.startswith("ART-")
        assert record.project_id == "PRJ-ABC"
        assert record.stage == "verification"
        assert record.status == "signed_off"
        assert record.author_id == author_id
        assert record.author == "eng@example.com"
        assert record.created_at is not None
        assert record.preview_url is None

    async def test_dict_content_is_serialized_to_json(self, store: MemoryArtifactStore) -> None:
        """Dict payloads are stored as a JSON string and round-trip cleanly."""
        record = await store.create_snapshot("PRJ-ABC", ArtifactStage.VERIFICATION, content=GEOMETRY)

        assert isinstance(record.content, str)
        assert json.loads(record.content) == GEOMETRY

    async def test_string_content_is_stored_verbatim(self, store: MemoryArtifactStore) -> None:
        """String payloads are passed through unchanged (already serialized)."""
        raw = json.dumps(GEOMETRY)
        record = await store.create_snapshot("PRJ-ABC", ArtifactStage.VERIFICATION, content=raw)

        assert record.content == raw

    async def test_accepts_stage_as_string(self, store: MemoryArtifactStore) -> None:
        """A raw stage string is normalized identically to the enum value."""
        record = await store.create_snapshot("PRJ-ABC", "analysis", content=GEOMETRY)

        assert record.stage == "analysis"

    async def test_each_snapshot_gets_a_unique_id(self, store: MemoryArtifactStore) -> None:
        a = await store.create_snapshot("PRJ-ABC", ArtifactStage.VERIFICATION, content=GEOMETRY)
        b = await store.create_snapshot("PRJ-ABC", ArtifactStage.VERIFICATION, content=GEOMETRY)

        assert a.artifact_id != b.artifact_id

    async def test_author_fields_default_to_none(self, store: MemoryArtifactStore) -> None:
        """Author is optional — anonymous snapshots are permitted."""
        record = await store.create_snapshot("PRJ-ABC", ArtifactStage.PARSING, content=GEOMETRY)

        assert record.author_id is None
        assert record.author is None


class TestListForProject:
    async def test_empty_when_no_artifacts(self, store: MemoryArtifactStore) -> None:
        assert await store.list_for_project("PRJ-NONE") == []

    async def test_returns_only_matching_project(self, store: MemoryArtifactStore) -> None:
        """Artifacts are isolated per project."""
        await store.create_snapshot("PRJ-A", ArtifactStage.VERIFICATION, content=GEOMETRY)
        await store.create_snapshot("PRJ-B", ArtifactStage.VERIFICATION, content=GEOMETRY)
        await store.create_snapshot("PRJ-A", ArtifactStage.ANALYSIS, content=GEOMETRY)

        a_records = await store.list_for_project("PRJ-A")
        b_records = await store.list_for_project("PRJ-B")

        assert len(a_records) == 2
        assert len(b_records) == 1
        assert all(r.project_id == "PRJ-A" for r in a_records)

    async def test_ordered_by_creation(self, store: MemoryArtifactStore) -> None:
        """Listing preserves creation order (oldest first)."""
        first = await store.create_snapshot("PRJ-A", ArtifactStage.PARSING, content=GEOMETRY)
        second = await store.create_snapshot("PRJ-A", ArtifactStage.VERIFICATION, content=GEOMETRY)
        third = await store.create_snapshot("PRJ-A", ArtifactStage.ANALYSIS, content=GEOMETRY)

        records = await store.list_for_project("PRJ-A")

        assert [r.artifact_id for r in records] == [
            first.artifact_id,
            second.artifact_id,
            third.artifact_id,
        ]


class TestGet:
    async def test_returns_matching_record(self, store: MemoryArtifactStore) -> None:
        created = await store.create_snapshot("PRJ-A", ArtifactStage.VERIFICATION, content=GEOMETRY)

        fetched = await store.get(created.artifact_id)

        assert fetched is not None
        assert fetched.artifact_id == created.artifact_id
        assert fetched.content == created.content

    async def test_returns_none_for_unknown_id(self, store: MemoryArtifactStore) -> None:
        assert await store.get("ART-DOESNOTEXIST") is None


class TestClear:
    async def test_clear_removes_all_artifacts(self, store: MemoryArtifactStore) -> None:
        await store.create_snapshot("PRJ-A", ArtifactStage.VERIFICATION, content=GEOMETRY)
        store.clear()

        assert await store.list_for_project("PRJ-A") == []
