"""Canonical NATS subject catalog.

All NATS subjects are built here, never hardcoded in services.
"""


def command_ready(device_id: str) -> str:
    return f"veyaan.command.ready.{device_id}"


def command_delivered(command_id: str) -> str:
    return f"veyaan.command.delivered.{command_id}"


def command_acknowledged(command_id: str) -> str:
    return f"veyaan.command.acknowledged.{command_id}"


def command_progress(command_id: str) -> str:
    return f"veyaan.command.progress.{command_id}"


def command_result(command_id: str) -> str:
    return f"veyaan.command.result.{command_id}"


def command_cancel(device_id: str) -> str:
    return f"veyaan.command.cancel.{device_id}"


def device_lifecycle(device_id: str) -> str:
    return f"veyaan.device.lifecycle.{device_id}"


def approval_decided(approval_id: str) -> str:
    return f"veyaan.approval.decided.{approval_id}"


def emergency_stop(owner_id: str) -> str:
    return f"veyaan.security.emergency_stop.{owner_id}"


def emergency_resume(owner_id: str) -> str:
    return f"veyaan.security.emergency_resume.{owner_id}"


# Stream subject patterns (used for stream config)
STREAM_COMMANDS_PATTERN = "veyaan.command.>"
STREAM_DEVICE_EVENTS_PATTERN = "veyaan.device.>"
STREAM_APPROVALS_PATTERN = "veyaan.approval.>"
STREAM_SECURITY_PATTERN = "veyaan.security.>"
