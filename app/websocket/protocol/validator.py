import json

from app.websocket.protocol.messages import (
    ClientMessage,
    CommandAckMessage,
    CommandProgressMessage,
    CommandResultMessage,
    DeviceStatusUpdateMessage,
    HeartbeatMessage,
    HelloMessage,
    ServerMessage,
)


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class ProtocolValidator:
    SUPPORTED_PROTOCOLS = ["v1"]
    MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB

    # Map message types to models
    TYPE_TO_MODEL = {
        "hello": HelloMessage,
        "heartbeat": HeartbeatMessage,
        "acknowledge": CommandAckMessage,
        "progress": CommandProgressMessage,
        "result": CommandResultMessage,
        "status_update": DeviceStatusUpdateMessage,
    }

    @classmethod
    def validate_protocol_version(cls, version: str) -> None:
        if version not in cls.SUPPORTED_PROTOCOLS:
            raise ProtocolError(
                "UNSUPPORTED_PROTOCOL",
                f"Protocol version '{version}' not supported. Supported: {cls.SUPPORTED_PROTOCOLS}",
            )

    @classmethod
    def validate_message_size(cls, data: bytes) -> None:
        if len(data) > cls.MAX_MESSAGE_SIZE:
            raise ProtocolError(
                "MESSAGE_TOO_LARGE", f"Message exceeds maximum size of {cls.MAX_MESSAGE_SIZE} bytes"
            )

    @classmethod
    def parse_client_message(cls, raw_data: bytes) -> ClientMessage:
        cls.validate_message_size(raw_data)
        try:
            data = json.loads(raw_data.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ProtocolError("INVALID_JSON", f"Invalid JSON: {e}") from None

        msg_type = data.get("type")
        if not msg_type:
            raise ProtocolError("MISSING_TYPE", "Message type is required")

        model = cls.TYPE_TO_MODEL.get(msg_type)
        if not model:
            raise ProtocolError("UNKNOWN_MESSAGE_TYPE", f"Unknown message type: {msg_type}")

        try:
            return model(**data)
        except Exception as e:
            raise ProtocolError("VALIDATION_ERROR", f"Invalid message format: {e}") from None

    @classmethod
    def serialize_server_message(cls, message: ServerMessage) -> bytes:
        data = message.model_dump(exclude_none=True, mode="json")
        return json.dumps(data).encode("utf-8")
