from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_audit_log(
        self,
        category: str,
        action: str,
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
    ):
        log = AuditLog(
            user_id=user_id,
            device_id=device_id,
            command_id=command_id,
            approval_id=approval_id,
            category=category,
            action=action,
            result=result,
            event_metadata=metadata,
            request_id=request_id,
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(log)
        await self.session.flush()
        return log

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
        query = select(AuditLog)

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if category:
            query = query.where(AuditLog.category == category)
        if action:
            query = query.where(AuditLog.action == action)
        if result:
            query = query.where(AuditLog.result == result)
        if device_id:
            query = query.where(AuditLog.device_id == device_id)
        if command_id:
            query = query.where(AuditLog.command_id == command_id)
        if start_date:
            query = query.where(AuditLog.created_at >= start_date)
        if end_date:
            query = query.where(AuditLog.created_at <= end_date)

        count_query = query.with_only_columns(func.count(AuditLog.id))
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        has_next = (page * page_size) < total
        has_prev = page > 1

        return items, total, has_next, has_prev
