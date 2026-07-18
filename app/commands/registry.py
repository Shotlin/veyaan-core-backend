from typing import Optional

from pydantic import BaseModel

from app.commands.models import RiskLevel
from app.commands.schemas import (
    DeviceStatusParams,
    EmergencyStopTestParams,
    OpenTestAppParams,
    PingParams,
    TakeScreenshotParams,
)


class CommandDefinition:
    def __init__(
        self,
        command_type: str,
        risk_level: RiskLevel,
        parameter_schema: type[BaseModel],
        requires_approval: bool = False,
        delayed_execution_allowed: bool = False,
        description: str = "",
    ):
        self.command_type = command_type
        self.risk_level = risk_level
        self.parameter_schema = parameter_schema
        self.requires_approval = requires_approval
        self.delayed_execution_allowed = delayed_execution_allowed
        self.description = description


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandDefinition] = {}

    def register(self, definition: CommandDefinition):
        self._commands[definition.command_type] = definition

    def get(self, command_type: str) -> Optional[CommandDefinition]:
        return self._commands.get(command_type)

    def get_all(self) -> dict[str, CommandDefinition]:
        return self._commands


# Initialize registry with test commands
command_registry = CommandRegistry()

# Low risk - no approval required
command_registry.register(CommandDefinition(
    command_type="system.ping",
    risk_level=RiskLevel.LOW,
    parameter_schema=PingParams,
    requires_approval=False,
    delayed_execution_allowed=True,
    description="Ping device to check connectivity",
))

command_registry.register(CommandDefinition(
    command_type="device.get_status",
    risk_level=RiskLevel.LOW,
    parameter_schema=DeviceStatusParams,
    requires_approval=False,
    delayed_execution_allowed=True,
    description="Get device status information",
))

# Medium risk - approval optional
command_registry.register(CommandDefinition(
    command_type="app.open_test",
    risk_level=RiskLevel.MEDIUM,
    parameter_schema=OpenTestAppParams,
    requires_approval=False,
    delayed_execution_allowed=True,
    description="Open a test application on device",
))

command_registry.register(CommandDefinition(
    command_type="system.take_test_screenshot",
    risk_level=RiskLevel.MEDIUM,
    parameter_schema=TakeScreenshotParams,
    requires_approval=False,
    delayed_execution_allowed=True,
    description="Take a test screenshot",
))

# High risk - approval required
command_registry.register(CommandDefinition(
    command_type="system.emergency_stop_test",
    risk_level=RiskLevel.HIGH,
    parameter_schema=EmergencyStopTestParams,
    requires_approval=True,
    delayed_execution_allowed=False,
    description="Test emergency stop activation",
))
