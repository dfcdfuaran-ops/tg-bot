"""Initialize Redis Stream consumer group for taskiq."""
import asyncio

from redis.asyncio import from_url

from src.core.config import AppConfig


async def init_consumer_group() -> None:
    """Initialize Redis Stream consumer group for taskiq on startup."""
    config = AppConfig.get()
    redis = await from_url(config.redis.dsn)
    try:
        await redis.xgroup_create(name="taskiq", groupname="taskiq", id="0", mkstream=True)
    except Exception as exc:
        # Consumer group might already exist, which is fine
        if "BUSYGROUP" not in str(exc):
            raise
    finally:
        await redis.close()


def init() -> None:
    """Sync wrapper for async init."""
    asyncio.run(init_consumer_group())
