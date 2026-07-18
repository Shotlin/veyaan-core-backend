"""
Typed domain error hierarchy for structured error handling.

Extends the flat ErrorCode enum with a richer exception hierarchy
that carries HTTP status, error code, and domain context together.
Service layers raise domain errors; API middleware converts to JSON.

Usage:
    from app.api.domain_errors import NotFoundError, ForbiddenError

    raise NotFoundError("command", command_id)
    raise ForbiddenError("Cannot access device owned by another user")
    raise ConflictError("Idempotency key reused with different payload")
"""

from typing import Any, Optional

from app.api.errors import ApiError, ErrorCode

# ---------------------------------------------------------------------------
# Base domain error
# ---------------------------------------------------------------------------


class DomainError(ApiError):
    """Base class for all structured domain errors."""

    default_code: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_status: int = 400

    def __init__(
        self,
        message: str,
        code: Optional[ErrorCode] = None,
        status_code: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(
            code=code or self.default_code,
            message=message,
            details=details,
            status_code=status_code or self.default_status,
        )


# ---------------------------------------------------------------------------
# 4xx Client Errors
# ---------------------------------------------------------------------------


class NotFoundError(DomainError):
    """Resource does not exist or is not accessible to the caller."""

    default_code = ErrorCode.NOT_FOUND
    default_status = 404

    def __init__(self, resource: str, resource_id: Any = None):
        msg = f"{resource} not found"
        if resource_id:
            msg = f"{resource} '{resource_id}' not found"
        super().__init__(
            message=msg,
            details={"resource": resource, "id": str(resource_id) if resource_id else None},
        )


class ForbiddenError(DomainError):
    """Caller is authenticated but does not have permission."""

    default_code = ErrorCode.FORBIDDEN
    default_status = 403

    def __init__(self, message: str = "Access denied", details: Optional[dict] = None):
        super().__init__(message=message, details=details)


class UnauthorizedError(DomainError):
    """Caller is not authenticated."""

    default_code = ErrorCode.INVALID_TOKEN
    default_status = 401

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message=message)


class ConflictError(DomainError):
    """Request conflicts with existing state (e.g. idempotency key reuse)."""

    default_code = ErrorCode.IDEMPOTENCY_CONFLICT
    default_status = 409

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message=message, details=details)


class ValidationError(DomainError):
    """Request payload is structurally invalid."""

    default_code = ErrorCode.VALIDATION_ERROR
    default_status = 422

    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else None
        super().__init__(message=message, details=details)


class RateLimitError(DomainError):
    """Too many requests from this client."""

    default_code = ErrorCode.RATE_LIMITED
    default_status = 429

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {"retry_after_seconds": retry_after} if retry_after else None
        super().__init__(message=message, details=details)


class LockedError(DomainError):
    """Resource is locked — e.g. emergency stop is active."""

    default_code = ErrorCode.EMERGENCY_STOP_ACTIVE
    default_status = 423

    def __init__(self, message: str = "Resource is locked"):
        super().__init__(message=message)


class InvalidStateError(DomainError):
    """Operation is not allowed in the resource's current state."""

    default_code = ErrorCode.INVALID_STATE
    default_status = 409

    def __init__(
        self, message: str, current_state: Optional[str] = None, target_state: Optional[str] = None
    ):
        details: dict = {}
        if current_state:
            details["current_state"] = current_state
        if target_state:
            details["target_state"] = target_state
        super().__init__(message=message, details=details or None)


# ---------------------------------------------------------------------------
# Domain-specific errors
# ---------------------------------------------------------------------------


class DeviceNotFoundError(NotFoundError):
    def __init__(self, device_id: Any = None):
        super().__init__("device", device_id)
        self.code = ErrorCode.DEVICE_NOT_FOUND


class DeviceRevokedError(ForbiddenError):
    def __init__(self, device_id: Any = None):
        super().__init__(
            f"Device {device_id} is not trusted",
            details={"device_id": str(device_id) if device_id else None},
        )
        self.code = ErrorCode.DEVICE_REVOKED
        self.status_code = 403


class CommandNotFoundError(NotFoundError):
    def __init__(self, command_id: Any = None):
        super().__init__("command", command_id)
        self.code = ErrorCode.COMMAND_NOT_FOUND


class CommandExpiredError(DomainError):
    default_code = ErrorCode.COMMAND_EXPIRED
    default_status = 410

    def __init__(self):
        super().__init__("Command has expired")


class ApprovalNotFoundError(NotFoundError):
    def __init__(self, approval_id: Any = None):
        super().__init__("approval", approval_id)
        self.code = ErrorCode.APPROVAL_NOT_FOUND


class ApprovalExpiredError(DomainError):
    default_code = ErrorCode.APPROVAL_EXPIRED
    default_status = 410

    def __init__(self):
        super().__init__("Approval has expired and can no longer be decided")


class ApprovalAlreadyDecidedError(ConflictError):
    def __init__(self, current_status: str):
        super().__init__(
            f"Approval was already {current_status}", details={"status": current_status}
        )
        self.code = ErrorCode.APPROVAL_ALREADY_DECIDED


class EmergencyStopActiveError(LockedError):
    def __init__(self):
        super().__init__("Emergency stop is active — commands are blocked")


class EmergencyStopNotActiveError(DomainError):
    default_code = ErrorCode.EMERGENCY_STOP_NOT_ACTIVE
    default_status = 400

    def __init__(self):
        super().__init__("Emergency stop is not currently active")


class PairingExpiredError(DomainError):
    default_code = ErrorCode.PAIRING_EXPIRED
    default_status = 410

    def __init__(self):
        super().__init__("Pairing code has expired")


class InvalidCredentialError(UnauthorizedError):
    def __init__(self):
        super().__init__("Invalid device credential")
        self.code = ErrorCode.INVALID_CREDENTIAL
        self.status_code = 401
