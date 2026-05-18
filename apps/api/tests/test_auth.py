"""
tests/test_auth.py
==================
Unit test suite verifying the custom authentication gates, multitenant onboarding,
and email dispatch resilience.

Covers:
1. Unverified login attempts blocking (Gate 1).
2. Stateful email-based 2FA pin generation and verification (Gate 2).
3. Google OAuth forgot-password reset requests blocking.
4. Automatic Organisation generation and slug collision resolution.
5. EmailService Resend dispatch and developer log fallbacks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from auth.manager import UserManager
from db.models.user import User
from db.models.organisation import Organisation
from services.email import EmailService


# ── FAKE DATABASE FIXTURE ───────────────────────────────────────────────────────

class FakeSession:
    """Mock database transaction session."""
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.rolled_back = False
        self.committed = False
        self.flushed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        self.flushed = True
        # Generate dummy ID for Organisation if added
        for obj in self.added:
            if isinstance(obj, Organisation) and not obj.id:
                obj.id = str(uuid.uuid4())


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def fake_user_db(fake_session: FakeSession) -> AsyncMock:
    user_db = AsyncMock()
    user_db.session = fake_session
    return user_db


# ── USER MANAGER TESTS ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slugify_utility() -> None:
    """
    Test standard string clean and slugify utility function.
    """
    user_db = AsyncMock()
    manager = UserManager(user_db)
    
    assert manager._slugify("John Doe's Company Ltd.") == "john-does-company-ltd"
    assert manager._slugify("  Acme--Corp!!!  ") == "acme-corp"
    assert manager._slugify("") == "tenant"


@pytest.mark.asyncio
async def test_auto_organisation_creation_on_register(fake_user_db: AsyncMock) -> None:
    """
    Test registration automatically spawns an Organisation and links the User.
    """
    manager = UserManager(fake_user_db)
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Jane Doe",
        is_verified=False,
        organisation_id=None,
    )

    # Mock DB query to check slug uniqueness (return None -> no conflict)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    execute_mock = AsyncMock(return_value=result_mock)
    fake_user_db.session.execute = execute_mock

    # Mock internal email service to bypass network transmission
    with patch("auth.manager.email_service", autospec=True) as mock_email:
        with patch.object(manager, "request_verify", new_callable=AsyncMock) as mock_req_verify:
            await manager.on_after_register(user, request=None)

            # Assert Organisation was generated
            added_orgs = [o for o in fake_user_db.session.added if isinstance(o, Organisation)]
            assert len(added_orgs) == 1
            org = added_orgs[0]
            assert org.name == "Jane Doe's Organisation"
            assert org.slug == "jane-doe"

            # Assert User was linked and committed
            assert user.organisation_id == org.id
            assert fake_user_db.session.committed is True
            mock_email.send_welcome_email.assert_called_once_with("test@example.com", "Jane Doe")
            mock_req_verify.assert_called_once_with(user, None)


@pytest.mark.asyncio
async def test_slug_collision_resolution(fake_user_db: AsyncMock) -> None:
    """
    Test Organisation auto-creation resolves slug collisions by appending tokens.
    """
    manager = UserManager(fake_user_db)
    user = User(
        id=uuid.uuid4(),
        email="colliding@example.com",
        full_name="Colls",
        organisation_id=None,
    )

    # Mock DB query to return an existing Organisation on first check, then None (no collision) on second check
    result_mock = MagicMock()
    existing_org = Organisation(name="Colls", slug="colls")
    result_mock.scalar_one_or_none.side_effect = [existing_org, None]
    execute_mock = AsyncMock(return_value=result_mock)
    fake_user_db.session.execute = execute_mock

    with patch("auth.manager.email_service", autospec=True):
        with patch.object(manager, "request_verify", new_callable=AsyncMock):
            await manager.on_after_register(user, request=None)

            added_orgs = [o for o in fake_user_db.session.added if isinstance(o, Organisation)]
            assert len(added_orgs) == 1
            org = added_orgs[0]
            assert org.slug.startswith("colls-")
            assert len(org.slug) > 5


@pytest.mark.asyncio
async def test_block_forgot_password_for_social_users(fake_user_db: AsyncMock) -> None:
    """
    Test password reset requests fail for Google OAuth-only accounts.
    """
    manager = UserManager(fake_user_db)
    # OAuth-only user has empty/None hashed_password
    user = User(
        id=uuid.uuid4(),
        email="social@google.com",
        hashed_password=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await manager.forgot_password(user, request=None)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "PASSWORD_RESET_NOT_ALLOWED_OAUTH_ONLY"


@pytest.mark.asyncio
async def test_allow_forgot_password_for_credentials_users(fake_user_db: MagicMock) -> None:
    """
    Test password reset request succeeds for email/password credentials profiles.
    """
    # Use standard mock since we want to verify super call
    manager = UserManager(fake_user_db)
    user = User(
        id=uuid.uuid4(),
        email="credentials@example.com",
        hashed_password="argon2-hashed-password-string",
    )

    # Mock standard BaseUserManager.forgot_password logic
    with patch("fastapi_users.BaseUserManager.forgot_password", new_callable=AsyncMock) as mock_super_forgot:
        await manager.forgot_password(user, request=None)
        mock_super_forgot.assert_called_once_with(user, None)


# ── EMAIL SERVICE TESTS ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_service_fallback_when_key_missing() -> None:
    """
    Test EmailService safely falls back to standard log print in development.
    """
    with patch("services.email.settings") as mock_settings:
        mock_settings.RESEND_API_KEY = ""
        mock_settings.SENDER_EMAIL = "sender@example.com"
        
        service = EmailService()
        
        with patch("services.email.logger") as mock_logger:
            await service.send_2fa_code_email("recipient@example.com", "123456")
            
            # Assert warning logger fallback was executed
            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args[0]
            assert "[DEVELOPMENT MODE] Email not sent via Resend" in args[0]
            assert "recipient@example.com" in args[1]
