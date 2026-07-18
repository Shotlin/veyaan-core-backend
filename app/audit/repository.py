from datetime import datetime
from typing import Optional, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.models import AuditAction, AuditCategory, AuditLog

T = TypeVar('T')


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_audit_log(
        self,
        category: AuditCategory,
        action: AuditAction,
        result: str,
        user_id: Optional[UUID] = None,
        device_id: Optional[UUID] = None,
        command_id: Optional[UUID] = None,
        approval_id: Optional[UUID] = None,
        metadata: Optional[str] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            user_id=user_id,
            device_id=device_id,
            command_id=command_id,
            approval_id=approval_id,
            category=category,
            action=action,
            result=result,
            metadata=metadata,
            request_id=request_id,
            trace_id=trace_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(audit_log)
        await self.session.flush()
        await self.session.refresh(audit_log)
        return audit_log

    async def query_audit_logs(
        self,
        user_id: Optional[UUID] = None,
        category: Optional[AuditCategory] = None,
        action: Optional[AuditAction] = None,
        result: Optional[str] = None,
        device_id: Optional[UUID] = None,
        command_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        query = select(AuditLog).options(
            selectinload(AuditLog.user),
            selectinload(AuditLog.device),
            selectinload(AuditLog.command),
            selectinload(AuditLog.approval),
        )

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

        query = query.order_by(AuditLog.created_at.desc())

        # Count total
        count_query = select(func.count(AuditLog.id))
        if user_id:
            count_query = count_query.where(AuditLog.user_id == user_id)
        if category:
            count_query = count_query.where(AuditLog.category == category)
        if action:
            count_query = count_query.where(AuditLog.action == action)
        if result:
            count_query = count_query.where(AuditLog.result == result)
        if device_id:
            count_query = count_query.where(AuditLog.device_id == device_id)
        if command_id:
            count_query = count_query.where(AuditLog.command_id == command_id)
        if start_date:
            count_query = count_query.where(AuditLog.created_at >= start_date)
        if end_date:
            count_query = count_query.where(AuditLog.created_at <= end_date)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        has_next = (page * page_size) < total
        has_prev = page > 1

        return items, total, has_next, has_prev
