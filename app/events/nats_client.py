import json
from typing import Any, Optional

import nats
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, RetentionPolicy, StreamConfig

from app.config import settings


class NatsClient:
    def __init__(self):
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None

    async def connect(self):
        self.nc = await nats.connect(
            settings.NATS_URL, reconnect_timewait=2, max_reconnect_attempts=-1
        )
        self.js = self.nc.jetstream()
        await self._ensure_streams()

    async def _ensure_streams(self):
        from app.events.subjects import (
            STREAM_APPROVALS_PATTERN,
            STREAM_COMMANDS_PATTERN,
            STREAM_DEVICE_EVENTS_PATTERN,
            STREAM_SECURITY_PATTERN,
        )

        streams = [
            StreamConfig(
                name=settings.NATS_STREAM_COMMANDS,
                subjects=[STREAM_COMMANDS_PATTERN],
                retention=RetentionPolicy.WORK_QUEUE,
                max_age=86400 * 7,
                max_msgs=1000000,
                storage="file",
                replicas=1,
                discard="old",
                duplicate_window=120 * 1_000_000_000,  # 2 minutes in nanos
            ),
            StreamConfig(
                name=settings.NATS_STREAM_DEVICE_EVENTS,
                subjects=[STREAM_DEVICE_EVENTS_PATTERN],
                retention=RetentionPolicy.LIMITS,
                max_age=86400 * 30,
                max_msgs=500000,
                storage="file",
            ),
            StreamConfig(
                name=settings.NATS_STREAM_APPROVALS,
                subjects=[STREAM_APPROVALS_PATTERN],
                retention=RetentionPolicy.LIMITS,
                max_age=86400 * 7,
                max_msgs=100000,
                storage="file",
            ),
            StreamConfig(
                name=settings.NATS_STREAM_SECURITY,
                subjects=[STREAM_SECURITY_PATTERN],
                retention=RetentionPolicy.LIMITS,
                max_age=86400 * 90,
                max_msgs=100000,
                storage="file",
            ),
        ]

        for stream_config in streams:
            try:
                await self.js.add_stream(stream_config)
            except Exception as e:
                if "stream name already in use" not in str(e):
                    raise

    async def disconnect(self):
        if self.nc:
            await self.nc.drain()
            await self.nc.close()

    async def publish_js(
        self,
        subject: str,
        payload: dict,
        message_id: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> None:
        if not self.js:
            raise RuntimeError("JetStream not connected")
        nats_headers = {}
        if headers:
            nats_headers.update(headers)
        if message_id:
            nats_headers["Nats-Msg-Id"] = message_id
        await self.js.publish(subject, json.dumps(payload).encode(), headers=nats_headers)

    async def subscribe_durable(self, subject: str, durable_name: str, stream: str) -> Any:
        if not self.js:
            raise RuntimeError("JetStream not connected")
        consumer = ConsumerConfig(
            durable_name=durable_name,
            ack_policy="explicit",
            max_deliver=3,
            ack_wait=30,
        )
        try:
            await self.js.add_consumer(stream, consumer)
        except Exception as e:
            if "consumer already exists" not in str(e):
                raise
        sub = await self.js.pull_subscribe(subject, durable=durable_name, stream=stream)
        return sub

    async def publish(self, subject: str, payload: bytes, headers: Optional[dict] = None) -> None:
        if not self.nc:
            raise RuntimeError("NATS not connected")
        await self.nc.publish(subject, payload, headers=headers)

    @property
    def is_connected(self) -> bool:
        return self.nc is not None and self.nc.is_connected


nats_client = NatsClient()
