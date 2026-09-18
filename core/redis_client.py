import redis

from core.config import settings

redis_client = redis.Redis.from_url(
    settings.REDIS_URL,
    socket_connect_timeout=5,
    socket_timeout=5,
)