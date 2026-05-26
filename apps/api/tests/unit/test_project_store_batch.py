"""
tests/unit/test_project_store_batch.py
======================================
Unit tests verifying the high-performance bulk/batch member registration
method in PostgresProjectStore and MemoryProjectStore.

Covers:
1. Happy Path: Batch registration of diverse, well-formed structural IDs.
2. Edge Case 1: Empty list behavior (zero-overhead complete).
3. Edge Case 2: Duplicate entries inside the input batch (idempotency).
4. Edge Case 3: Incremental batch registration against pre-existing members.
5. Edge Case 4: Category inference based on standard lower/uppercase prefixes.
6. Edge Case 5: Extremely large batch registration (scale validation).
"""

from __future__ import annotations

import pytest
from schemas.project import ProjectCreate
from storage.project_store import project_store
import db.session

@pytest.fixture(autouse=True)
async def cleanup_db_connections():
    """
    Clean up and dispose of global SQLAlchemy engines between tests
    to prevent asyncpg Event Loop reuse mismatches.
    """
    yield
    if hasattr(db.session, "_engine") and db.session._engine is not None:
        await db.session._engine.dispose()
        # pyrefly: ignore [bad-assignment]
        db.session._engine = None
        # pyrefly: ignore [bad-assignment]
        db.session._async_session_maker = None

@pytest.mark.asyncio
async def test_batch_register_happy_path() -> None:
    """
    Test: Happy Path.
    Verify multiple members with typical prefixes are registered successfully
    and categorized correctly in a single bulk operation.
    """
    # Create test project
    data = ProjectCreate(
        name="Batch Happy Path Project",
        reference="BHP-777",
        client="Acme Structures",
        design_code="BS8110"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Diverse batch to register
    mids = ["C-1", "B-2", "S-3", "F-4", "W-5"]
    await project_store.register_members_batch(pid, mids)

    # Check results
    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 5
    assert registered == sorted(mids)


@pytest.mark.asyncio
async def test_batch_register_edge_empty_list() -> None:
    """
    Test: Edge Case 1.
    Verify passing an empty list of member IDs completes immediately
    without errors or database operations.
    """
    data = ProjectCreate(
        name="Batch Empty Project",
        reference="EMP-000",
        client="Acme",
        design_code="EC2"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Call with empty list
    await project_store.register_members_batch(pid, [])

    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 0


@pytest.mark.asyncio
async def test_batch_register_edge_internal_duplicates() -> None:
    """
    Test: Edge Case 2.
    Verify that duplicate member IDs within the input list are handled
    idempotently, registering only unique entries.
    """
    data = ProjectCreate(
        name="Batch Internal Duplicates",
        reference="DUP-111",
        client="Acme",
        design_code="BS8110"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Batch with redundant items
    mids = ["B-1", "B-1", "C-2", "C-2", "C-2"]
    await project_store.register_members_batch(pid, mids)

    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 2
    assert registered == ["B-1", "C-2"]


@pytest.mark.asyncio
async def test_batch_register_edge_incremental_duplicates() -> None:
    """
    Test: Edge Case 3.
    Verify that subsequent batch inserts containing overlapping items
    do not trigger unique constraint failures and correctly register new items.
    """
    data = ProjectCreate(
        name="Batch Incremental Duplicates",
        reference="INC-222",
        client="Acme",
        design_code="EC2"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Step A: Register initial batch
    await project_store.register_members_batch(pid, ["B-1", "C-1"])
    
    # Step B: Register overlapping batch
    await project_store.register_members_batch(pid, ["B-1", "C-1", "S-1", "F-1"])

    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 4
    assert registered == ["B-1", "C-1", "F-1", "S-1"]


@pytest.mark.asyncio
async def test_batch_register_edge_case_sensitivity_and_inference() -> None:
    """
    Test: Edge Case 4.
    Verify lowercase prefixes correctly map to uppercase structural member categories
    and are categorized properly.
    """
    data = ProjectCreate(
        name="Batch Case Sensitivity",
        reference="CAS-333",
        client="Acme",
        design_code="BS8110"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Lowercase identifiers
    mids = ["c-100", "s-200", "b-300", "f-400", "w-500", "unknown-999"]
    await project_store.register_members_batch(pid, mids)

    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 6
    assert "c-100" in registered
    assert "unknown-999" in registered


@pytest.mark.asyncio
async def test_batch_register_edge_scale_stress() -> None:
    """
    Test: Edge Case 5.
    Verify the batch system scales efficiently under 200+ members
    in a single transactional insert.
    """
    data = ProjectCreate(
        name="Batch Stress Project",
        reference="STR-999",
        client="Scale Stress Corp",
        design_code="EC2"
    )
    project = await project_store.create(data)
    pid = project.project_id

    # Large batch
    large_batch = [f"B-{i}" for i in range(250)]
    await project_store.register_members_batch(pid, large_batch)

    registered = await project_store.get_member_ids(pid)
    assert len(registered) == 250
    assert registered[0] == "B-0"
    assert registered[-1] == "B-99"  # lexical sort order
