from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()

# HTTP metrics
http_requests_total = Counter(
    "veyaan_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)

http_request_duration = Histogram(
    "veyaan_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=registry,
)

# Command metrics
commands_created_total = Counter(
    "veyaan_commands_created_total",
    "Total commands created",
    ["command_type", "risk_level", "state"],
    registry=registry,
)

command_duration = Histogram(
    "veyaan_command_duration_seconds",
    "Command execution duration",
    ["command_type"],
    registry=registry,
)

# Device metrics
device_connected = Gauge(
    "veyaan_device_connected", "Device connection status", ["device_id"], registry=registry
)

# Queue metrics
outbox_pending = Gauge("veyaan_outbox_pending", "Pending outbox events", registry=registry)

nats_consumer_lag = Gauge(
    "veyaan_nats_consumer_lag", "NATS consumer lag", ["consumer", "stream"], registry=registry
)

# Emergency stop
emergency_stop_active = Gauge(
    "veyaan_emergency_stop_active", "Emergency stop active", ["user_id"], registry=registry
)
