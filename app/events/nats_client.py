
import nats
from nats.js.api import ConsumerConfig, RetentionPolicy, StreamConfig

from app.config import settings


class NatsClient:
    def __init__(self):
        self.nc: nats.NATS | None = None
        self.js = None

    async def connect(self):
        self.nc = await nats.connect(settings.NATS_URL)
        self.js = self.nc.jetstream()
        await self._setup_streams()

    async def _setup_streams(self):
        streams = [
            StreamConfig(
                name=settings.NATS_STREAM_COMMANDS,
                subjects=["veyaan.commands.>"],
                retention=RetentionPolicy.WORK_QUEUE,
                max_age=86400 * 7,
                max_msgs=1000000,
                storage="file",
                replicas=1
            ),
            StreamConfig(
                name=settings.NATS_STREAM_DEVICE_EVENTS,
                subjects=["veyaan.device.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=86400 * 30,
                storage="file"
            ),
            StreamConfig(
                name=settings.NATS_STREAM_APPROVALS,
                subjects=["veyaan.approvals.>"],
                retention=RetentionPolicy.WORK_QUEUE,
                max_age=86400 * 7,
                storage="file"
            ),
            StreamConfig(
                name=settings.NATS_STREAM_SECURITY,
                subjects=["veyaan.security.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=86400 * 90,
                storage="file"
            )
        ]

        for stream_config in streams:
            try:
                await self.js.add_stream(stream_config)
            except Exception as e:
                if "stream name already in use" not in str(e):
                    raise

        # Create consumers
        consumers = [
            ConsumerConfig(
                durable_name=settings.NATS_CONSUMER_GATEWAY,
                filter_subject="veyaan.commands.ready",
                ack_policy="explicit",
                max_deliver=3,
                ack_wait=30
            ),
            ConsumerConfig(
                durable_name=settings.NATS_CONSUMER_API,
                filter_subject="veyaan.commands.result.>",
                ack_policy="explicit",
                max_deliver=3,
                ack_wait=30
            )
        ]

        for consumer in consumers:
            try:
                await self.js.add_consumer(settings.NATS_STREAM_COMMANDS, consumer)
            except Exception as e:
                if "consumer already exists" not in str(e):
                    raise

    async def disconnect(self):
        if self.nc:
            await self.nc.close()


nats_client = NatsClient()
