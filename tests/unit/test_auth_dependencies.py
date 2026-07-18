"""Unit tests for authentication dependencies.

Tests JWT validation, user context resolution, suspended accounts,
and missing/expired/invalid token handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claims(sub: str = None, email: str = "test@example.com"):
    claims = MagicMock()
    claims.sub = sub or str(uuid4())
    claims.email = email
    return claims


def _make_user(status: str = "active"):
    user = MagicMock()
    user.id = uuid4()
    user.supabase_user_id = str(uuid4())
    user.email = "test@example.com"
    user.status = MagicMock()
    user.status.value = status
    return user


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

class TestGetCurrentToken:

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_401(self):
        from app.api.errors import ApiError
        from app.auth.dependencies import get_current_token
        with pytest.raises(ApiError) as exc_info:
            await get_current_token(credentials=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_credentials_returns_token(self):
        from app.auth.dependencies import get_current_token
        creds = MagicMock()
        creds.credentials = "valid-jwt-token"
        result = await get_current_token(credentials=creds)
        assert result == "valid-jwt-token"


# ---------------------------------------------------------------------------
# User context resolution
# ---------------------------------------------------------------------------

class TestGetCurrentUserContext:

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_context(self):
        from app.auth.dependencies import get_current_user_context
        from app.auth.user_context import UserContext

        claims = _make_claims()
        user = _make_user("active")

        with patch("app.auth.dependencies.supabase_auth") as mock_auth, \
             patch("app.auth.dependencies.UserRepository") as mock_repo_class:

            mock_auth.verify_token = AsyncMock(return_value=claims)
            mock_repo = AsyncMock()
            mock_repo.get_by_supabase_id = AsyncMock(return_value=user)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            result = await get_current_user_context(
                token="valid-token",
                session=mock_session,
            )

        assert isinstance(result, UserContext)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_new_user_created_on_first_login(self):
        from app.auth.dependencies import get_current_user_context

        claims = _make_claims()
        new_user = _make_user("active")

        with patch("app.auth.dependencies.supabase_auth") as mock_auth, \
             patch("app.auth.dependencies.UserRepository") as mock_repo_class:

            mock_auth.verify_token = AsyncMock(return_value=claims)
            mock_repo = AsyncMock()
            # First call returns None (user doesn't exist yet)
            mock_repo.get_by_supabase_id = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(return_value=new_user)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            result = await get_current_user_context(
                token="valid-token",
                session=mock_session,
            )

        mock_repo.create.assert_called_once_with(claims.sub, claims.email)
        assert result.id == new_user.id

    @pytest.mark.asyncio
    async def test_suspended_user_raises_403(self):
        from app.api.errors import ApiError
        from app.auth.dependencies import get_current_user_context

        claims = _make_claims()
        suspended_user = _make_user("suspended")

        with patch("app.auth.dependencies.supabase_auth") as mock_auth, \
             patch("app.auth.dependencies.UserRepository") as mock_repo_class:

            mock_auth.verify_token = AsyncMock(return_value=claims)
            mock_repo = AsyncMock()
            mock_repo.get_by_supabase_id = AsyncMock(return_value=suspended_user)
            mock_repo_class.return_value = mock_repo

            mock_session = AsyncMock()
            with pytest.raises(ApiError) as exc_info:
                await get_current_user_context(token="valid-token", session=mock_session)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_token_propagates_error(self):
        from app.api.errors import ApiError
        from app.auth.dependencies import get_current_user_context

        with patch("app.auth.dependencies.supabase_auth") as mock_auth:
            mock_auth.verify_token = AsyncMock(
                side_effect=ApiError(
                    code="INVALID_TOKEN",
                    message="Token expired",
                    status_code=401,
                )
            )

            mock_session = AsyncMock()
            with pytest.raises(ApiError) as exc_info:
                await get_current_user_context(token="expired-token", session=mock_session)

        assert exc_info.value.status_code == 401
