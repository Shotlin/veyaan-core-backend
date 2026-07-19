"""Audit service — session-aware implementation.

The service accepts an existing AsyncSession and uses it for all writes.
It does NOT open its own session or commit — the outer business service
owns the transaction boundary.

For read-only queries (e.g., API list routes), pass the request-scoped
session injected via Depends(get_db_session).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditAction, AuditCategory
from app.audit.repository import AuditRepository
from app.database.session import get_db_session_context as _get_db_session


class AuditService:
    """Session-aware audit service.

    Pass an existing session to share the business transaction::

        audit = AuditService(session)
        await audit.create_audit_log(...)
        await session.commit()  # caller commits

    For standalone read queries you may omit the session and the service
    will open its own read-only session::

        audit = AuditService()
        logs = await audit.query_audit_logs(...)
    """

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

    async def create_audit_log(
        self,
        category: AuditCategory,
        action: AuditAction,
        result: str,
        user_id: Optional[UUID] = None,
        device_id: Optional[UUID] = None,
        command_id: Optional[UUID] = None,
        approval_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Insert an audit row using the shared session.

        Does NOT commit — the caller commits after their full business
        transaction is complete.
        """
        if self._session is None:
            raise RuntimeError(
                "AuditService requires a session for write operations. "
                "Pass session=... to AuditService()."
            )
        repo = AuditRepository(self._session)
        await repo.create_audit_log(
            category=category.value if isinstance(category, AuditCategory) else category,
            action=action.value if isinstance(action, AuditAction) else action,
            result=result,
            user_id=user_id,
            device_id=device_id,
            command_id=command_id,
            approval_id=approval_id,
            metadata=metadata,
            request_id=request_id,
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # No commit here — caller owns the transaction.

    async def query_audit_logs(
        self,
        user_id: Optional[UUID] = None,
        category: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        device_id: Optional[UUID] = None,
        command_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        """Read-only log query.

        If this service was constructed with a session, use it.
        Otherwise, open a dedicated read session.
        """
        if self._session is not None:
            repo = AuditRepository(self._session)
            return await repo.query_audit_logs(
                user_id=user_id,
                category=category,
                action=action,
                result=result,
                device_id=device_id,
                command_id=command_id,
                start_date=start_date,
                end_date=end_date,
                page=page,
                page_size=page_size,
            )

        async with _get_db_session() as session:
            repo = AuditRepository(session)
            return await repo.query_audit_logs(
                user_id=user_id,
                category=category,
                action=action,
                result=result,
                device_id=device_id,
                command_id=command_id,
                start_date=start_date,
                end_date=end_date,
                page=page,
                page_size=page_size,
            )
