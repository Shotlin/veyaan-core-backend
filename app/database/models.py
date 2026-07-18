"""Central import for all mapped models to ensure Alembic autogeneration detects them."""

from app.approvals.models import Approval  # noqa: F401
from app.audit.models import AuditLog  # noqa: F401
from app.commands.models import Command, CommandStateEvent, Task  # noqa: F401
from app.devices.models import Device, DeviceCredential, PairingRequest  # noqa: F401
from app.emergency_stop.models import EmergencyStop  # noqa: F401
from app.events.outbox_models import OutboxEvent  # noqa: F401
from app.users.models import User  # noqa: F401
