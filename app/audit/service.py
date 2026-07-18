from datetime import datetime
from typing import Optional
from uuid import UUID

from app.audit.models import AuditAction, AuditCategory
from app.audit.repository import AuditRepository
from app.database.session import get_db_session


class AuditService:
    def __init__(self):
        pass

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
        async with get_db_session() as session:
            repo = AuditRepository(session)
            await repo.create_audit_log(
                category=category,
                action=action,
                result=result,
                user_id=user_id,
                device_id=device_id,
                command_id=command_id,
                approval_id=approval_id,
                metadata=str(metadata) if metadata else None,
                request_id=request_id,
                trace_id=trace_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await session.commit()

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
        async with get_db_session() as session:
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
