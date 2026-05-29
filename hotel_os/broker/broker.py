# ============================================================
# HotelOS — Message Broker (Redis Pub/Sub wrapper)
#
# All inter-service communication goes through here.
# Services NEVER call each other directly — only publish/subscribe.
#
# Usage (publisher):
#   await broker.publish(Events.ROOM_VACATED, {"room": 204})
#
# Usage (subscriber — runs as background task):
#   async for message in broker.subscribe(Events.ROOM_VACATED):
#       handle(message)
# ============================================================

import json
import asyncio
import logging
from typing import Any, AsyncIterator, Callable

import redis.asyncio as aioredis

from shared.config import REDIS_URL

logger = logging.getLogger("hotelos.broker")


class MessageBroker:
    """
    Thin async wrapper around Redis Pub/Sub.
    One shared connection pool for publish,
    a fresh connection per subscriber channel.
    """

    def __init__(self, url: str = REDIS_URL):
        self._url = url
        self._redis: aioredis.Redis | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the shared Redis connection."""
        self._redis = await aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Broker connected to Redis at %s", self._url)

    async def disconnect(self) -> None:
        """Close the shared Redis connection."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Broker disconnected from Redis")

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """
        Serialize payload to JSON and publish on the given channel.
        Always wraps payload with the channel name for easy routing.
        """
        if self._redis is None:
            raise RuntimeError("Broker not connected — call await broker.connect() first")

        message = json.dumps({"channel": channel, "data": payload})
        receivers = await self._redis.publish(channel, message)
        logger.debug("Published on '%s' → %d receiver(s) | payload: %s", channel, receivers, payload)

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        *channels: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Async generator — yields decoded message dicts whenever a
        message arrives on any of the given channels.

        Example:
            async for msg in broker.subscribe("room.vacated"):
                room_number = msg["data"]["room_number"]
        """
        # Each subscriber needs its own connection to avoid blocking publish
        sub_redis = await aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        pubsub = sub_redis.pubsub()
        await pubsub.subscribe(*channels)
        logger.info("Subscribed to channels: %s", channels)

        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    yield json.loads(raw["data"])
                except json.JSONDecodeError:
                    logger.warning("Broker received non-JSON message: %s", raw["data"])
        finally:
            await pubsub.unsubscribe(*channels)
            await sub_redis.aclose()

    # ------------------------------------------------------------------
    # Pattern Subscribe (wildcard)
    # ------------------------------------------------------------------

    async def psubscribe(self, pattern: str) -> AsyncIterator[dict[str, Any]]:
        """
        Pattern-based subscribe — e.g. psubscribe('room.*') receives
        room.vacated, room.status_changed, room.assigned, etc.
        """
        sub_redis = await aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        pubsub = sub_redis.pubsub()
        await pubsub.psubscribe(pattern)
        logger.info("Pattern-subscribed: %s", pattern)

        try:
            async for raw in pubsub.listen():
                if raw["type"] != "pmessage":
                    continue
                try:
                    yield json.loads(raw["data"])
                except json.JSONDecodeError:
                    logger.warning("Broker received non-JSON pmessage: %s", raw["data"])
        finally:
            await pubsub.punsubscribe(pattern)
            await sub_redis.aclose()


# ------------------------------------------------------------------
# Helper — run a subscriber handler as a background task
# ------------------------------------------------------------------

async def run_subscriber(
    broker: MessageBroker,
    channels: list[str],
    handler: Callable[[dict[str, Any]], Any],
) -> None:
    """
    Convenience wrapper: subscribe to channels and call handler for each message.
    Designed to be launched with asyncio.create_task().

    Args:
        broker:   connected MessageBroker instance
        channels: list of channel names to subscribe to
        handler:  async or sync callable — receives the full message dict
    """
    async for message in broker.subscribe(*channels):
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(message)
            else:
                handler(message)
        except Exception as exc:
            logger.error("Subscriber handler error on channel '%s': %s", message.get("channel"), exc)


# ------------------------------------------------------------------
# Module-level singleton — imported by all services
# ------------------------------------------------------------------

broker = MessageBroker()
